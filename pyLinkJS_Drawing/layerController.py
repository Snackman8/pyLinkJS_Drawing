# --------------------------------------------------
#    Imports
# --------------------------------------------------
import concurrent.futures
import datetime
import logging
import threading
import time
import traceback
import pandas as pd
from pyLinkJS_Drawing.drawingPlugin import JSDraw, ImageObject, RectObject
from pylinkjs.PyLinkJS import get_broadcast_jsclients


# --------------------------------------------------
#    Classes
# --------------------------------------------------
class LayerRenderer():
    def __init__(self, name, starting_data_dict={}, subscribed_datasources=[]):
        """ init for LayerRenderer

            Public Attributes:
                name - unique name of this LayerRenderer
                subscribed datasources - list of layer datasource names this renderer subscribes to

            Args:
                name - unique name of this LayerRenderer
                starting_data_dict - starting data for this renderer in order to perform layer init
                subscribed datasources - list of layer datasource names this renderer subscribes to
        """
        self._data = self._data_dict_to_df(starting_data_dict)
        self.name = name
        self.subscribed_datasources = list(subscribed_datasources)
        self.visible = True

    @classmethod
    def _data_dict_to_df(cls, data_dict):
        """ convert a dictionary of dataframes into a giant dataframe

            Args:
                data_dict - dictionary of dataframes

            Returns:
                dataframe which is a union of all the dataframes in the dictionary
        """
        # init
        keys = list(data_dict.keys())
        if len(keys) == 0:
            return pd.DataFrame()

        # build union of indexes
        idx = data_dict[keys[0]].index
        for k in keys[1:]:
            idx = idx.union(data_dict[k].index)
        idx = idx.drop_duplicates(keep='last')

        # init return dataframe
        df = pd.DataFrame(index=idx)

        # add in all the data
        for k in keys:
            df_new = data_dict[k][~data_dict[k].index.duplicated(keep='last')]
            for c in df_new.columns:
                df[c] = df_new[c]

        # intersection with data_coords
        df = df.loc[data_dict['data_coords'].index]

        # success!
        return df

    def get_options(self):
        return []

    def get_tooltip(self, wx, wy, rolist):
        return ''

    def layer_init(self):
        """ Initialize render objects

            Args:
                initial_data_coords - dataframe containing x, y coordinates for data objects
                parentObj - object to create render objects on
        """
        raise NotImplemented()

    def on_data_changed(self, data_dict):
        """ Callback when subscribed data changes

            Args:
                data_dict - dictionary of dataframes from data sources.
        """
        # merge the data
        self._data = self._data_dict_to_df(data_dict)

    def render(self, parentObj, options):
        """ update properties on data objects for rendering """
        raise NotImplemented()


class LayerDataSource():
    def __init__(self, name, cooldown_period=5, next_fire_time=datetime.datetime(1900, 1, 1), initial_data=pd.DataFrame()):
        """ init for a LayerDatasource

            Public Attributes:
                cooldown_period - number of seconds to wait between the end of the previous data fetch and the next data fetch
                data - dataframe containing the data from the last data fetch
                data_last_fetch_time - the datetime of the last data fetch
                name - unique name of this layer data source
                next_fire_time - datetime of the earliest time this datasource can fetch data again


            Args:
                name - name of the Layer Data Source
                cooldown_period - number of seconds to cooldown between data requests, cooldown begins when the previous data
                                  fetch returns
                next_fire_time - initial first fire time for the data source.  Defaults to firing as soon as possible.
                                 set to None to disable firing
                initial_data - initial data
        """
        self.cooldown_period = cooldown_period
        self.data = initial_data
        self.data_last_fetch_time = None
        self.name = name
        self.next_fire_time = next_fire_time

    @classmethod
    def data_fetch(cls):
        """ Fetch data for this data source

            Returns:
                dataframe
        """
        raise NotImplemented()

    def set_data(self, df, data_fetch_time=None):
        """ set the data for this data source

            Args:
                df - data to set
                data_fetch_time - date and time of the last completed data fetch.  None to use now
        """
        self.data = df
        self.data_last_fetch_time = datetime.datetime.now() if data_fetch_time is None else data_fetch_time


class LayerController:
    def __init__(self, minimum_datasource_cooldown_period=5):
        self._layer_datasources = {}
        self._layer_datarenderers = {}
        self.shutdown = False
        self.minimum_datasource_cooldown_period = minimum_datasource_cooldown_period

    @classmethod
    def _mp_wrapper(cls, func, args, kwargs, q):
        retval = func(*args, **kwargs)
        q.put(retval)

    def start(self):
        t = threading.Thread(target=self._thread_worker, args=())
        t.start()

    def _status_message_for_datasource(self, ds):
        html = f'<h4>{ds.name}</h4>'
        if ds.data_last_fetch_time:
            delta = (datetime.datetime.now() - ds.data_last_fetch_time).seconds
            if delta < 180:
                html += f'{delta} seconds ago'
            else:
                html += f'{(delta / 60):3.1f} minutes ago'

        return html

    def build_options_html(self, jsc):
        html = ''
        opts = {}
        for dr in self._layer_datarenderers.values():
            for opt in dr.get_options():
                if opt['type'] == 'Boolean':
                    checked = ''
                    if opt['default_value']:
                        checked = 'checked'
                    html += f"""<input type="checkbox" id="opt_{opt['id']}" name="opt_{opt['id']}" value="{opt['id']}" onclick="call_py('options_changed');" {checked}>{opt['text']}<br>"""
                    opts[opt['id']] = opt['default_value']
        jsc.tag['options'] = opts
        return html

    def get_datasource_status_messages(self):
        keys = list(self._layer_datasources.keys())
        status_html = ''
        for k in keys:
            status_html += self._status_message_for_datasource(self._layer_datasources[k])
        return status_html

    def get_tooltip(self, layer_names, tooltip_idx):
        html = ''
        for name in layer_names:
            if name in self._layer_datarenderers:
                try:
                    html += self._layer_datarenderers[name].get_tooltip(tooltip_idx)
                except Exception as e:
                    html += repr(e) + '<br>'
        return html

    def render(self, parentObj, options):
        # notify renderers that data source has been updated
        for dr in self._layer_datarenderers.values():
            try:
                dr.render(parentObj, options)
            except:
                logging.error(traceback.format_exc())

    def update_options(self, jsc):
        # read back all of the options
        opts = {}
        for dr in self._layer_datarenderers.values():
            for opt in dr.get_options():
                if opt['type'] == 'Boolean':
                    optval = jsc.eval_js_code(f"""$('#opt_{opt['id']}').is(":checked")""")
                    opts[opt['id']] = optval
        jsc.tag['options'] = opts

    def _thread_worker(self):
        """ thread worker, coordinate data fetches """

        # setup the process pool executor
        futures = {}
        with concurrent.futures.ProcessPoolExecutor(len(self._layer_datasources)) as executor:
            while not self.shutdown:
                # loop through all the available data sources
                keys = list(self._layer_datasources.keys())
                for k in keys:
                    # mark the current time
                    current_time = datetime.datetime.now()

                    # check if this jobs can fire based on time
                    ds = self._layer_datasources[k]
                    if (ds.next_fire_time is not None) and (current_time >= ds.next_fire_time):
                        # clear the next fire time so we do not accidently refire while running
                        ds.next_fire_time = None
                        ds.fire_start_time = current_time
                        fut = executor.submit(ds.__class__.data_fetch)
                        futures[ds.name] = fut

                # check processes for completion
                dirty_renderers = set()
                for k in list(futures.keys()):
                    # continue if the future is not ready
                    if not futures[k].done():
                        continue

                    # future is ready so process
                    ds = self._layer_datasources[k]
                    try:
                        ds.set_data(futures[k].result())
                    except:
                        logging.error(traceback.format_exc())
                    del futures[k]
                    logging.info(f"""{ds.name} data ready""")
                    ds.next_fire_time = ds.data_last_fetch_time + datetime.timedelta(seconds=max(ds.cooldown_period, self.minimum_datasource_cooldown_period))

                    # notify renderers that the data has changed
                    for dr in self._layer_datarenderers.values():
                        if ds.name in dr.subscribed_datasources:
                            dirty_renderers.add(dr.name)

                # update dirty renderers
                for name in list(dirty_renderers):
                    dr = self._layer_datarenderers[name]
                    data_dict = {}
                    for dn in dr.subscribed_datasources:
                        data_dict[dn] = self._layer_datasources[dn].data
                    try:
                        dr.on_data_changed(data_dict)
                    except:
                        logging.error(traceback.format_exc())

                # one second frequency
                time.sleep(1)


class LayerApp:
    def __init__(self, data_sources, renderers):
        self.layer_controller = LayerController(minimum_datasource_cooldown_period=3)

        for lds in data_sources:
            self.layer_controller._layer_datasources[lds.name] = lds

        for lr in renderers:
            self.layer_controller._layer_datarenderers[lr.name] = lr

        self.layer_controller.start()

    @classmethod
    def compute_image_scale(cls, w, h):
        if w < h:
            scale = 2000.0 / h
        else:
            scale = 2000.0 / w

        return (w * scale, h * scale)

    @classmethod
    def compute_zoom(cls, canvas_width, canvas_height, image_width, image_height):
        c_ar = canvas_width / canvas_height
        i_ar = image_width / image_height

        if c_ar < i_ar:
            # fit to image width
            return canvas_width / image_width
        else:
            # fit to image height
            return canvas_height / image_height

    def on_mouseup(self, jsc, x, y, button):
        """ print out the click coordinate """
#        global DATA_CLICK_INDEX

        if (button == 0):
#            print(f'{DATA_CLICK_PREFIX}-{DATA_CLICK_INDEX},{int(x)},{int(y)}')
#            DATA_CLICK_INDEX = DATA_CLICK_INDEX + 1

            if 'ROOT_RENDER_OBJECT' in jsc.tag:
                # check if we need to move the tool tip
                mlp = jsc.eval_js_code(f"""mouse_get_last_position();""")
                if mlp is not None:
                    t = time.time()
                    rolist = jsc.tag['ROOT_RENDER_OBJECT'].point_in_obj(mlp['wx'], mlp['wy'], t)

                    # assemble a layer list
                    tooltip_idx = None
                    layer_names = set()
                    for ro in rolist:
                        if 'layer_name' in ro.props:
                            layer_names.add(ro.props['layer_name'])
                            if 'idx' in ro.props:
                                tooltip_idx = ro.props['idx']

                    jsc.tag['property_window'] = {'layer_names': layer_names, 'idx': tooltip_idx}

                    html = self.layer_controller.get_tooltip(layer_names, tooltip_idx)
                    jsc['#properties'].html = html

    def on_options_changed(self, jsc):
        self.layer_controller.update_options(jsc)

    def on_ready(self, jsc, background_image_path, drawing_context_name, display_context_name):
        # create the render objects list
        f = jsc.drawing()
        f.create_image('img_floor_plan', background_image_path)
        f.render(jsc)

        # get the canvas width and canvas height
        canvas_width = jsc.eval_js_code(f'{drawing_context_name}.canvas.width')
        canvas_height = jsc.eval_js_code(f'{drawing_context_name}.canvas.height')

        # wait for image to load
        img_width, img_height = canvas_width, canvas_height
        start_time = time.time()
        while (time.time() - start_time) < 5:
            if jsc.eval_js_code('img_floor_plan.complete'):
                img_width = jsc.eval_js_code('img_floor_plan.naturalWidth')
                img_height = jsc.eval_js_code('img_floor_plan.naturalHeight')
                break

        # attempt to scale the image up to a normalized coordinate system of 2000 x 2000
        img_width, img_height = LayerApp.compute_image_scale(img_width, img_height)

        # calcualte zoom
        zoom = LayerApp.compute_zoom(canvas_width, canvas_height, img_width, img_height)

        # set the initial zoom to fit the image
        jsc.eval_js_code(f"""force_zoom({drawing_context_name}.canvas.id, {display_context_name}.canvas.id, 0, 0, {zoom});""")
        jsc.eval_js_code(f"""force_translate({drawing_context_name}.canvas.id, {display_context_name}.canvas.id, {(canvas_width / zoom - img_width) / 2}, {(canvas_height / zoom - img_height) / 2});""")

        # create the background
        root_obj = RectObject(flightplan=None, x=0, y=0, width=canvas_width, height=canvas_height, strokeStyle='rgba(0, 0, 0, 0)', fillStyle='rgba(0, 0, 0, 0)', clickable=False)

        # create the background
        image_obj = ImageObject(name='img', flightplan=None, x=0, y=0, width=img_width, height=img_height, image_name='img_floor_plan', filter_str='opacity(0.2)')
        root_obj.add_child(image_obj)
        jsc.tag['ROOT_RENDER_OBJECT'] = root_obj

        # initialize the layer renderers for this jsc
        for dr in self.layer_controller._layer_datarenderers.values():
            dr.layer_init(image_obj)

        # generate html for layer selection
        jsc['#options'].html = self.layer_controller.build_options_html(jsc)
        self.layer_controller.update_options(jsc)

        # render
        f.render(jsc)

    def start(self):
        # start the thread
        t = threading.Thread(target=self.thread_worker, daemon=True)
        t.start()

    def thread_worker(self):
        # init
        last_render_refresh_time = 0
        last_status_refresh_time = 0
        last_tooltip_check_time = 0
        last_property_refresh_time = 0

        # loop forever
        while True:
            t = time.time()

            try:
                # refresh the data visually if needed
                if (t - last_render_refresh_time) > 0.1:
                    for jsc in get_broadcast_jsclients('/'):

                        # refresh the render objects associated with the data
                        if 'ROOT_RENDER_OBJECT' in jsc.tag:
                            image_obj = jsc.tag['ROOT_RENDER_OBJECT'].children['img']
                            self.layer_controller.render(image_obj, jsc.tag.get('options', []))

                            f = JSDraw('ctx_drawing', 'ctx_display')
                            f.fillStyle = 'white'
                            f.clear()
                            jsc.tag['ROOT_RENDER_OBJECT'].render(f, t)
                            f.render(jsc)
                    last_render_refresh_time = time.time()


                if (t - last_tooltip_check_time) > 0.1:
                    for jsc in get_broadcast_jsclients('/'):
                        if 'ROOT_RENDER_OBJECT' in jsc.tag:
                            # check if we need to move the tool tip
                            mlp = jsc.eval_js_code(f"""mouse_get_last_position();""")
                            if mlp is not None:
                                if mlp['elapsed_ms'] > 500:
                                    t = time.time()
                                    rolist = jsc.tag['ROOT_RENDER_OBJECT'].point_in_obj(mlp['wx'], mlp['wy'], t)

                                    # assemble a layer list
                                    tooltip_idx = None
                                    layer_names = set()
                                    for ro in rolist:
                                        if 'layer_name' in ro.props:
                                            layer_names.add(ro.props['layer_name'])
                                            if 'idx' in ro.props:
                                                tooltip_idx = ro.props['idx']

                                    html = self.layer_controller.get_tooltip(layer_names, tooltip_idx)
                                    if html != '':
                                        jsc['#tooltip'].html = html
                                        jsc['#tooltip'].css.left = mlp['px']
                                        jsc['#tooltip'].css.top = mlp['py']
                                        jsc['#tooltip'].css.visibility = 'visible'
                                        jsc['body'].css.cursor = 'crosshair'
                                    else:
                                        jsc['#tooltip'].css.visibility = 'hidden'
                                        jsc['body'].css.cursor = 'default'
                                else:
                                    jsc['#tooltip'].css.visibility = 'hidden'
                                    jsc['body'].css.cursor = 'default'
                    last_tooltip_check_time = time.time()

                # refresh property window if needed
                if (t - last_property_refresh_time) > 1:
                    for jsc in get_broadcast_jsclients('/'):
                        if 'property_window' in jsc.tag:
                            layer_names = jsc.tag['property_window']['layer_names']
                            idx = jsc.tag['property_window']['idx']
                            html = self.layer_controller.get_tooltip(layer_names, idx)
                            jsc['#properties'].html = html

                # refresh the status if needed
                if (t - last_status_refresh_time) > 1:
                    for jsc in get_broadcast_jsclients('/'):
                        jsc['#datasources'].html = self.layer_controller.get_datasource_status_messages()
                    last_status_refresh_time = time.time()

                # sleep 10ms
                time.sleep(0.01)
            except Exception as e:
                print(e)
                time.sleep(60)
