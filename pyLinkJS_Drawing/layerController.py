"""Layer orchestration framework for pyLinkJS_Drawing.

Defines base classes for datasources and renderers, coordinates periodic data
fetch/update flow, and manages interactive layer app behavior (render refresh,
tooltips, options, and datasource status updates) for pyLinkJS canvas clients.
"""

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
    """Base class for renderers that map datasource state to render objects."""
    def __init__(self, name, starting_data_dict=None, subscribed_datasources=None):
        """Initialize a data-driven layer renderer.

        Args:
            name: Required unique renderer name.
            starting_data_dict: Initial source dataframe mapping. Defaults to
                an empty mapping when ``None``.
            subscribed_datasources: Datasource names consumed by this renderer.
                Defaults to an empty list when ``None``.

        Returns:
            None.

        Note:
            - ``self.visible`` is initialized to ``True``.
        """
        if starting_data_dict is None:
            starting_data_dict = {}
        if subscribed_datasources is None:
            subscribed_datasources = []

        self._data = self._data_dict_to_df(starting_data_dict)
        self.name = name
        self.subscribed_datasources = list(subscribed_datasources)
        self.visible = True

    @classmethod
    def _data_dict_to_df(cls, data_dict):
        """Merge multiple source dataframes into a single dataframe.

        Args:
            data_dict: Dictionary of dataframes keyed by datasource name.

        Returns:
            Dataframe containing merged columns and aligned index values.

        Note:
            - ``data_dict`` is expected to include a ``data_coords`` key used
              to constrain the final index set.
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
        """Return renderer-specific option descriptors.

        Returns:
            Iterable of option descriptor dictionaries.
        """
        return {}

    def get_tooltip(self, wx, wy, rolist):
        """Return tooltip HTML for a hit-test result set.

        Args:
            wx: World-space mouse x coordinate.
            wy: World-space mouse y coordinate.
            rolist: Render objects under cursor.

        Returns:
            HTML string for tooltip display.
        """
        return ''

    def layer_init(self):
        """Initialize render objects for this layer.

        Returns:
            None.

        Note:
            - Subclasses must implement this method.
        """
        raise NotImplemented()

    def on_data_changed(self, data_dict):
        """Handle updates from subscribed datasources.

        Args:
            data_dict: Dataframe mapping for subscribed datasources.

        Returns:
            None.
        """
        # merge the data
        self._data = self._data_dict_to_df(data_dict)

    def render(self, parentObj, options):
        """Update layer-owned render objects before frame draw.

        Args:
            parentObj: Parent render object this layer updates.
            options: Runtime options map for conditional rendering.

        Returns:
            None.

        Note:
            - Subclasses must implement this method.
        """
        raise NotImplemented()


class LayerDataSource():
    """Base class for polling datasource providers used by layer renderers."""
    def __init__(self, name, cooldown_period=5, next_fire_time=datetime.datetime(1900, 1, 1), initial_data=None):
        """Initialize a polling datasource for one layer input stream.

        Args:
            name: Required unique datasource name.
            cooldown_period: Minimum seconds between completed fetches.
                Default is ``5``.
            next_fire_time: Earliest allowed fetch time. Default is
                ``datetime.datetime(1900, 1, 1)`` to fire immediately on start.
                Set ``None`` to disable polling.
            initial_data: Initial dataframe value. Defaults to an empty
                dataframe when ``None``.

        Returns:
            None.

        Note:
            - ``self.data_last_fetch_time`` is initialized to ``None`` until
              ``set_data`` is called.
        """
        if initial_data is None:
            initial_data = pd.DataFrame()

        self.cooldown_period = cooldown_period
        self.data = initial_data
        self.data_last_fetch_time = None
        self.name = name
        self.next_fire_time = next_fire_time

    @classmethod
    def data_fetch(cls):
        """Fetch the latest dataframe for this datasource.

        Returns:
            Dataframe for this datasource.

        Note:
            - Subclasses must implement this method.
        """
        raise NotImplemented()

    def set_data(self, df, data_fetch_time=None):
        """Set the most recent dataframe and fetch timestamp.

        Args:
            df: Dataframe to store as current datasource data.
            data_fetch_time: Completion timestamp for the fetch operation.
                Uses ``datetime.datetime.now()`` when ``None``.

        Returns:
            None.

        Note:
            - This method updates both ``self.data`` and
              ``self.data_last_fetch_time``.
        """
        self.data = df
        self.data_last_fetch_time = datetime.datetime.now() if data_fetch_time is None else data_fetch_time


class LayerController:
    """Coordinates datasource polling and renderer update callbacks."""
    def __init__(self, minimum_datasource_cooldown_period=5):
        """Initialize datasource/renderer coordination state.

        Args:
            minimum_datasource_cooldown_period: Global floor for datasource
                cooldown intervals in seconds. Default is ``5``.

        Returns:
            None.
        """
        self._layer_datasources = {}
        self._layer_datarenderers = {}
        self.shutdown = False
        self.minimum_datasource_cooldown_period = minimum_datasource_cooldown_period

    @classmethod
    def _mp_wrapper(cls, func, args, kwargs, q):
        """Run a callable and push its return value into a queue.

        Args:
            func: Callable to execute.
            args: Positional arguments for ``func``.
            kwargs: Keyword arguments for ``func``.
            q: Queue-like object that supports ``put``.

        Returns:
            None.
        """
        retval = func(*args, **kwargs)
        q.put(retval)

    def start(self):
        """Start the datasource polling worker thread.

        Returns:
            None.
        """
        t = threading.Thread(target=self._thread_worker, args=())
        t.start()

    def _status_message_for_datasource(self, ds):
        """Build HTML status text for one datasource.

        Args:
            ds: ``LayerDataSource`` instance to summarize.

        Returns:
            HTML snippet containing datasource name and recency text.
        """
        html = f'<h4>{ds.name}</h4>'
        if ds.data_last_fetch_time:
            delta = (datetime.datetime.now() - ds.data_last_fetch_time).seconds
            if delta < 180:
                html += f'{delta} seconds ago'
            else:
                html += f'{(delta / 60):3.1f} minutes ago'

        return html

    def build_options_html(self, jsc):
        """Build options-panel HTML from all registered renderers.

        Args:
            jsc: Active pyLinkJS client.

        Returns:
            HTML string with option controls.
        """
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
        """Return concatenated datasource status HTML.

        Returns:
            HTML string for datasource status panel.
        """
        keys = list(self._layer_datasources.keys())
        status_html = ''
        for k in keys:
            status_html += self._status_message_for_datasource(self._layer_datasources[k])
        return status_html

    def get_tooltip(self, layer_names, tooltip_idx):
        """Collect tooltip HTML from matching renderers.

        Args:
            layer_names: Iterable of renderer names to query.
            tooltip_idx: Data index used by renderer tooltip handlers.

        Returns:
            HTML string combining renderer tooltip fragments.
        """
        html = ''
        for name in layer_names:
            if name in self._layer_datarenderers:
                try:
                    html += self._layer_datarenderers[name].get_tooltip(tooltip_idx)
                except Exception as e:
                    html += repr(e) + '<br>'
        return html

    def render(self, parentObj, options):
        """Run ``render`` on each registered layer renderer.

        Args:
            parentObj: Parent render object passed to renderers.
            options: Runtime options map.

        Returns:
            None.
        """
        # notify renderers that data source has been updated
        for dr in self._layer_datarenderers.values():
            try:
                dr.render(parentObj, options)
            except:
                logging.error(traceback.format_exc())

    def update_options(self, jsc):
        """Read option control state from browser and store in ``jsc.tag``.

        Args:
            jsc: Active pyLinkJS client.

        Returns:
            None.
        """
        # read back all of the options
        opts = {}
        for dr in self._layer_datarenderers.values():
            for opt in dr.get_options():
                if opt['type'] == 'Boolean':
                    optval = jsc.eval_js_code(f"""$('#opt_{opt['id']}').is(":checked")""")
                    opts[opt['id']] = optval
        jsc.tag['options'] = opts

    def _thread_worker(self):
        """Run the datasource polling loop and fan out updates to renderers.

        Returns:
            None.

        Note:
            - Uses ``ProcessPoolExecutor`` with one worker per registered
              datasource.
        """

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
    """High-level app wrapper for interactive layered drawing views."""
    def __init__(self, data_sources, renderers):
        """Initialize the layer app and register datasources/renderers.

        Args:
            data_sources: Iterable of ``LayerDataSource`` instances.
            renderers: Iterable of ``LayerRenderer`` instances.

        Returns:
            None.

        Note:
            - Creates a ``LayerController`` with minimum cooldown ``3`` and
              starts controller polling immediately.
        """
        self.layer_controller = LayerController(minimum_datasource_cooldown_period=3)

        for lds in data_sources:
            self.layer_controller._layer_datasources[lds.name] = lds

        for lr in renderers:
            self.layer_controller._layer_datarenderers[lr.name] = lr

        self.layer_controller.start()

    @classmethod
    def compute_image_scale(cls, w, h):
        """Scale image dimensions to fit a 2000-unit max side.

        Args:
            w: Original image width.
            h: Original image height.

        Returns:
            Tuple ``(scaled_width, scaled_height)``.
        """
        if w < h:
            scale = 2000.0 / h
        else:
            scale = 2000.0 / w

        return (w * scale, h * scale)

    @classmethod
    def compute_zoom(cls, canvas_width, canvas_height, image_width, image_height):
        """Compute zoom factor that fits image inside canvas bounds.

        Args:
            canvas_width: Canvas width in pixels.
            canvas_height: Canvas height in pixels.
            image_width: Image width in world units.
            image_height: Image height in world units.

        Returns:
            Scalar zoom factor.
        """
        c_ar = canvas_width / canvas_height
        i_ar = image_width / image_height

        if c_ar < i_ar:
            # fit to image width
            return canvas_width / image_width
        else:
            # fit to image height
            return canvas_height / image_height

    def on_mouseup(self, jsc, x, y, button):
        """Handle mouse-up events and refresh property panel selection.

        Args:
            jsc: Active pyLinkJS client.
            x: World-space mouse x coordinate.
            y: World-space mouse y coordinate.
            button: Mouse button value from browser event.

        Returns:
            None.

        Note:
            - Only left-click events (``button == 0``) update the property
              panel state.
        """
        if (button == 0):
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
        """Handle options panel changes for one client.

        Args:
            jsc: Active pyLinkJS client.

        Returns:
            None.
        """
        self.layer_controller.update_options(jsc)

    def on_ready(self, jsc, background_image_path, drawing_context_name, display_context_name):
        """Initialize canvas scene, layers, options, and first render.

        Args:
            jsc: Active pyLinkJS client.
            background_image_path: Background image URL/path.
            drawing_context_name: Off-screen canvas context variable name.
            display_context_name: On-screen canvas context variable name.

        Returns:
            None.
        """
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

        # calculate zoom
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
        """Start the UI refresh worker thread.

        Returns:
            None.
        """
        # start the thread
        t = threading.Thread(target=self.thread_worker, daemon=True)
        t.start()

    def thread_worker(self):
        """Run periodic rendering, tooltip, property, and status refresh loops.

        Returns:
            None.
        """
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
                            self.layer_controller.render(image_obj, jsc.tag.get('options', {}))

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
                logging.error(e)
                time.sleep(60)
