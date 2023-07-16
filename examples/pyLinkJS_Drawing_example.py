# --------------------------------------------------
#    Imports
# --------------------------------------------------
import argparse
import datetime
import random
import threading
import logging
import pandas as pd
from pylinkjs.PyLinkJS import run_pylinkjs_app, get_broadcast_jsclients
from pyLinkJS_Drawing.drawingPlugin import *
from pyLinkJS_Drawing.layerController import LayerController, LayerDataSource, LayerRenderer


# --------------------------------------------------
#    Globals
# --------------------------------------------------
DATA_CLICK_PREFIX = 'H'
DATA_CLICK_INDEX = 9
LAYER_CONTROLLER = None


# --------------------------------------------------
#    Function
# --------------------------------------------------
def compute_image_scale(w, h):
    if w < h:
        scale = 2000.0 / h
    else:
        scale = 2000.0 / w

    return (w * scale, h * scale)


def compute_zoom(canvas_width, canvas_height, image_width, image_height):
    c_ar = canvas_width / canvas_height
    i_ar = image_width / image_height

    if c_ar < i_ar:
        # fit to image width
        return canvas_width / image_width
    else:
        # fit to image height
        return canvas_height / image_height


# --------------------------------------------------
#    Event Handlers
# --------------------------------------------------
def onmouseup(jsc, x, y, button):
    """ print out the click coordinate """
    global DATA_CLICK_INDEX

    if (button == 0):
        print(f'{DATA_CLICK_PREFIX}-{DATA_CLICK_INDEX},{int(x)},{int(y)}')
        DATA_CLICK_INDEX = DATA_CLICK_INDEX + 1

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

                html = LAYER_CONTROLLER.get_tooltip(layer_names, tooltip_idx)
                jsc['#properties'].html = html


def options_changed(jsc, *args):
    LAYER_CONTROLLER.update_options(jsc)


def ready(jsc, *args):
    """ called when a webpage creates a new connection the first time on load """
    # create the render objects list
    f = jsc.drawing()
    f.create_image('img_floor_plan', jsc.tag['background_file'])
    f.render(jsc)

    # get the canvas width and canvas height
    canvas_width = jsc.eval_js_code('ctx1.canvas.width')
    canvas_height = jsc.eval_js_code('ctx1.canvas.height')

    # wait for image to load
    img_width, img_height = canvas_width, canvas_height
    start_time = time.time()
    while (time.time() - start_time) < 5:
        if jsc.eval_js_code('img_floor_plan.complete'):
            img_width = jsc.eval_js_code('img_floor_plan.naturalWidth')
            img_height = jsc.eval_js_code('img_floor_plan.naturalHeight')
            break

    # attempt to scale the image up to a normalized coordinate system of 2000 x 2000
    img_width, img_height = compute_image_scale(img_width, img_height)

    # calcualte zoom
    zoom = compute_zoom(canvas_width, canvas_height, img_width, img_height)

    # set the initial zoom to fit the image
    jsc.eval_js_code(f"""force_zoom('Canvas1', 'Canvas2', 0, 0, {zoom});""")
    jsc.eval_js_code(f"""force_translate('Canvas1', 'Canvas2', {(canvas_width / zoom - img_width) / 2}, {(canvas_height / zoom - img_height) / 2});""")

    # create the background
    root_obj = RectObject(flightplan=None, x=0, y=0, width=canvas_width, height=canvas_height, strokeStyle='rgba(0, 0, 0, 0)', fillStyle='rgba(0, 0, 0, 0)', clickable=False)

    # create the background
    image_obj = ImageObject(name='img', flightplan=None, x=0, y=0, width=img_width, height=img_height, image_name='img_floor_plan', filter_str='opacity(0.2)')
    root_obj.add_child(image_obj)
    jsc.tag['ROOT_RENDER_OBJECT'] = root_obj

    # initialize the layer renderers for this jsc
    for dr in LAYER_CONTROLLER._layer_datarenderers.values():
        dr.layer_init(image_obj)

    # generate html for layer selection
    jsc['#options'].html = LAYER_CONTROLLER.build_options_html(jsc)
    LAYER_CONTROLLER.update_options(jsc)

    # render
    f.render(jsc)


def reconnect(jsc, *args):
    """ called when a webpage automatically reconnects a broken connection """
    print('Reconnect', args)
    ready(jsc)


# --------------------------------------------------
#    Layer Implementation
# --------------------------------------------------
class LDS_Example_Values(LayerDataSource):
#    FAKE_DATA = pd.DataFrame(columns=['Value', 'Value_ts', 'PrevValue', 'FirstSeen_ts'], index=[f'D-{i}' for i in range(1, 15)]).fillna(0)

    def __init__(self, cooldown_period=5):
        """ init """
        super().__init__(name='ExampleValues', cooldown_period=cooldown_period)

    @classmethod
    def data_fetch(cls):
        """ fake fetch data """
        time.sleep(1)
        # hacky way to make fake persistent data
        try:
            df = pd.read_csv('Values.csv', index_col=0)
        except:
            print('Error!')
            df = pd.DataFrame(columns=['Value', 'Value_ts', 'PrevValue', 'FirstSeen_ts'], index=[f'D-{i}' for i in range(1, 15)]).fillna(0)

        # save the previous values
        df.index.name = 'index'
        df['Value_ts'] = pd.to_datetime(df['Value_ts'])
        df['FirstSeen_ts'] = pd.to_datetime(df['FirstSeen_ts'])
        df['PrevValue'] = df['Value']

        # update the values
        for _ in range(0, random.randint(1, 6)):
            idx = f'D-{random.randint(1, 14)}'
            df.loc[idx, 'Value'] = random.randint(0, 200)
            df.loc[idx, 'Value_ts'] = datetime.datetime.now() - datetime.timedelta(minutes=random.randint(1, 10))

        # fix the firstSeen_ts as needed
        df.loc[df['Value'] != df['PrevValue'], 'FirstSeen_ts'] = datetime.datetime.now()

        # save
        df.to_csv('Values.csv')

        return df


class LDS_Example_Open(LayerDataSource):
    def __init__(self, cooldown_period=5):
        """ init """
        super().__init__(name='ExampleOpen', cooldown_period=cooldown_period)

    @classmethod
    def data_fetch(cls):
        """ fake fetch data """
        time.sleep(10)
        idx = []
        open_vals = []
        for _ in range(0, random.randint(12, 13)):
            idx.append(f'D-{random.randint(1,13)}')
            open_vals.append(random.choice([True, False]))
        df = pd.DataFrame(data={'Open': open_vals, 'index': idx}).drop_duplicates(subset='index', keep='last').set_index('index')
        return df


class LR_Example_Circle(LayerRenderer):
    def layer_init(self, parentObj):
        for idx, r in self._data.iterrows():
            circle_obj = CircleObject(name=f'CIRCLE_{idx}', x=r['x'], y=r['y'], radius=1, fillStyle='black', lineWidth=0.1, layer_name=self.name)
            parentObj.add_child(circle_obj)

    def get_options(self):
        return [{'id': 'circle', 'text': 'Example Circle', 'type': 'Boolean', 'default_value': True}]

    def get_tooltip(self, tooltip_idx):
#        idx = None
        html = ''
        # for ro in rolist:
        #     if 'idx' in ro.props:
        #         idx = ro.props['idx']
        html += 'Radius: ' + str(self._data.loc[tooltip_idx].circle_radius) + '<br>'
#                break
        return html

    def on_data_changed(self, data_dict):
        # merge the data
        df = self._data_dict_to_df(data_dict)

        if 'Value' in df.columns:
            df['Value'] = df['Value'].fillna(0)
            # compute the radius and color of the circle
            df['circle_radius'] = df.apply(lambda x: max(3, x['Value'] / 20.0), axis=1)
            df['circle_fillStyle'] = 'rgba(0, 255, 0, 0.2)'
            df.loc[df['Value'] < 20, 'circle_fillStyle'] = 'rgba(255, 0, 255, 0.2)'

        if 'Open' in df.columns:
            df['Open'] = df['Open'].fillna(False)
            df.loc[~(df['Open'] == True), 'circle_radius'] = 2
            df.loc[~(df['Open'] == True), 'circle_fillStyle'] = 'rgba(192, 192, 192, 0.5)'

        self._data = df

    def render(self, parentObj, options):
        if 'circle_radius' not in self._data.columns:
            return

        visible = options['circle']

        for idx, r in self._data.iterrows():
            if (circleObj := parentObj.children.get(f'CIRCLE_{idx}', None)) is not None:
                circleObj.props['visible'] = visible
                circleObj.props['radius'] = r['circle_radius']
                circleObj.props['fillStyle'] = r['circle_fillStyle']


class LR_Example_Text(LayerRenderer):
    def layer_init(self, parentObj):
        click_width = 15
        click_height = 12
        for idx, r in self._data.iterrows():
            click_obj = RectObject(name=f'CLICK_{idx}', x=r['x'] - click_width / 2, y=r['y']- click_height / 2, width=click_width, height=click_height, strokeStyle='rgba(0, 0, 0, 0)', fillStyle='rgba(0, 0, 0, 0)', clickable=True, layer_name=self.name, idx=idx)
            text_obj = TextObject(name=f'TEXT_{idx}', x=r['x'], y=r['y'], text_str='?', lineWidth=0.1, fillStyle='black', font='8pt Arial', textAlign='center', textBaseline='middle', layer_name=self.name, idx=idx)
            parentObj.add_child(click_obj)
            parentObj.add_child(text_obj)

    def get_options(self):
        return [{'id': 'text', 'text': 'Example Text', 'type': 'Boolean', 'default_value': True},
                {'id': 'always_red', 'text': 'Always Red', 'type': 'Boolean', 'default_value': False}]

    def get_tooltip(self, tooltip_idx):
        html = ''
        html += tooltip_idx + '<br>'
        html += 'Value: ' + str(self._data.loc[tooltip_idx].Value) + '<br>'
        html += 'TimeStamp: ' + str(self._data.loc[tooltip_idx].Value_ts) + '<br>'
        return html

    def on_data_changed(self, data_dict):
        # merge the data
        df = self._data_dict_to_df(data_dict)

        df['text_fillStyle'] = 'black'
        df['text_font'] = '8pt Arial'

        if 'Value' in df.columns:
            df['Value'] = df['Value'].fillna(0)
            df['text_str'] = df['Value'].astype('int').astype('str')

            for idx, r in df.iterrows():
                if (datetime.datetime.now() - r['FirstSeen_ts']).seconds < 5:
                    df.loc[idx, 'text_fillStyle'] = 'blue'
                    df.loc[idx, 'text_font'] = '12pt Arial'
                else:
                    df.loc[idx, 'text_fillStyle'] = 'black'
                    df.loc[idx, 'text_font'] = '8pt Arial'

        if 'Open' in df.columns:
            df['Open'] = df['Open'].fillna(False)
            df.loc[~(df['Open'] == True), 'text_str'] = ''

        self._data = df

    def render(self, parentObj, options):
        if 'text_fillStyle' not in self._data.columns:
            return

        visible = options['text']

        for idx, r in self._data.iterrows():
            if (textObj := parentObj.children.get(f'TEXT_{idx}', None)) is not None:
                textObj.props['visible'] = visible
                textObj.props['text_str'] = r['text_str']
                textObj.props['fillStyle'] = r['text_fillStyle']
                textObj.props['font'] = r['text_font']

                if options['always_red'] == True:
                    textObj.props['fillStyle'] = 'red'


# --------------------------------------------------
#    Main
# --------------------------------------------------
def start_threaded_automatic_update():
    """ example of how to run a periodic update from a different thread """
    def thread_worker():
        # init
        last_render_refresh_time = 0
        last_status_refresh_time = 0
        last_tooltip_check_time = 0
        last_property_refresh_time = 0

        # loop forever
        while True:
            t = time.time()

            # refresh the data visually if needed
            if (t - last_render_refresh_time) > 0.1:
                for jsc in get_broadcast_jsclients('/'):

                    # refresh the render objects associated with the data
                    if 'ROOT_RENDER_OBJECT' in jsc.tag:
                        image_obj = jsc.tag['ROOT_RENDER_OBJECT'].children['img']
                        LAYER_CONTROLLER.render(image_obj, jsc.tag['options'])

                        f = JSDraw('ctx1', 'ctx2')
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

                                html = LAYER_CONTROLLER.get_tooltip(layer_names, tooltip_idx)
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
                        html = LAYER_CONTROLLER.get_tooltip(layer_names, idx)
                        jsc['#properties'].html = html

            # refresh the status if needed
            if (t - last_status_refresh_time) > 1:
                for jsc in get_broadcast_jsclients('/'):
                    jsc['#datasources'].html = LAYER_CONTROLLER.get_datasource_status_messages()
                last_status_refresh_time = time.time()

            # sleep 10ms
            time.sleep(0.01)

    # start the thread
    t = threading.Thread(target=thread_worker, daemon=True)
    t.start()


# --------------------------------------------------
#    Main
# --------------------------------------------------
def main(args):
    global LAYER_CONTROLLER

    # init the google oauth2 plugin
    drawing_plugin = pluginDrawing('ctx1', 'ctx2')

    LAYER_CONTROLLER = LayerController(minimum_datasource_cooldown_period=3)

    # read the data coordinate file
    data_coord_file = os.path.join(os.path.dirname(__file__), args['data_coordinate_file'])
    df_data_coords = pd.read_csv(data_coord_file, index_col=0)
    lds_data_coords = LayerDataSource(name='data_coords', next_fire_time=None, initial_data=df_data_coords)
    lds_value = LDS_Example_Values(cooldown_period=1)
    lds_open = LDS_Example_Open(cooldown_period=1)
    LAYER_CONTROLLER._layer_datasources[lds_data_coords.name] = lds_data_coords
    LAYER_CONTROLLER._layer_datasources[lds_value.name] = lds_value
    LAYER_CONTROLLER._layer_datasources[lds_open.name] = lds_open

    lr_circle = LR_Example_Circle(name='circle', starting_data_dict={'data_coords': df_data_coords}, subscribed_datasources=[lds_data_coords.name, lds_value.name, lds_open.name] )
    lr_text = LR_Example_Text(name='text', starting_data_dict={'data_coords': df_data_coords}, subscribed_datasources=[lds_data_coords.name, lds_value.name, lds_open.name] )
    LAYER_CONTROLLER._layer_datarenderers[lr_circle.name] = lr_circle
    LAYER_CONTROLLER._layer_datarenderers[lr_text.name] = lr_text

    LAYER_CONTROLLER.start()

    start_threaded_automatic_update()
    run_pylinkjs_app(default_html='pyLinkJS_Drawing_example.html', extra_settings={'background_file': args['background_file'], 'data_coordinates_file': args['data_coordinate_file']}, plugins=[drawing_plugin])


if __name__ == '__main__':
    # start the thread and the app
    logging.basicConfig(level=logging.DEBUG, format='%(relativeCreated)6d %(threadName)s %(message)s')

    # parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--background_file', help='file location of the background image', default='floor_plan.svg')
    parser.add_argument('--data_coordinate_file', help='file location of the data coordiantes', default='data_coords.csv')
    args = parser.parse_args()
    args = vars(args)

    # run the main
    main(args)
