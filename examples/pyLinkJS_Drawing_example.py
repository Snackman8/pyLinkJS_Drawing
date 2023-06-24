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

        t = time.time()

        ro = jsc.tag['ROOT_RENDER_OBJECT'].point_in_obj(x, y, t)
        if hasattr(ro, 'click_handler'):
            ro.click_handler(ro)
            return

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

    # render
    f.render(jsc)


# --------------------------------------------------
#    Layer Implementation
# --------------------------------------------------
class LDS_Example_Values(LayerDataSource):
    def __init__(self, cooldown_period=0):
        """ init """
        super().__init__(name='ExampleValues', cooldown_period=cooldown_period)
    
    @classmethod
    def data_fetch(cls):
        """ fake fetch data """
        time.sleep(0.1)
        idx = []
        values = []
        ts = []
        for _ in range(0, random.randint(6, 13)):
            idx.append(f'D-{random.randint(1,13)}')
            values.append(random.randint(0, 200))
            ts.append(datetime.datetime.now())
        df = pd.DataFrame(data={'Value': values, 'index': idx, 'Value_ts': ts}).set_index('index').drop_duplicates()
        return df


class LDS_Example_Open(LayerDataSource):
    def __init__(self, cooldown_period=0):
        """ init """
        super().__init__(name='ExampleOpen', cooldown_period=cooldown_period)
    
    @classmethod
    def data_fetch(cls):
        """ fake fetch data """
        time.sleep(0.1)
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
            circle_obj = CircleObject(name=f'CIRCLE_{idx}', x=r['x'], y=r['y'], radius=1, fillStyle='black', lineWidth=0.1)
            parentObj.add_child(circle_obj)

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

    def render(self, parentObj):
        if 'circle_radius' not in self._data.columns:
            return

        for idx, r in self._data.iterrows():
            if (circleObj := parentObj.children.get(f'CIRCLE_{idx}', None)) is not None:
                circleObj.props['radius'] = r['circle_radius']
                circleObj.props['fillStyle'] = r['circle_fillStyle']


class LR_Example_Text(LayerRenderer):
    def layer_init(self, parentObj):
        for idx, r in self._data.iterrows():
            text_obj = TextObject(name=f'TEXT_{idx}', x=r['x'], y=r['y'], text_str='?', lineWidth=0.1, fillStyle='black', font='8pt Arial', textAlign='center', textBaseline='middle')
            parentObj.add_child(text_obj)

    def on_data_changed(self, data_dict):
        # merge the data
        df = self._data_dict_to_df(data_dict)

        df['text_fillStyle'] = 'black'
        df['text_font'] = '8pt Arial'

        if 'Value' in df.columns:
            df['Value'] = df['Value'].fillna(0) 
            df['text_str'] = df['Value'].astype('int').astype('str')

            # d = datetime.datetime.now()
            # for idx, r in df.iterrows():
            #     print(pd.Timedelta(d - r['Value_ts']).seconds)
            #     if pd.Timedelta(d - r['Value_ts']).seconds < 5:
            #         df.loc[idx, 'textFillStyle'] = 'black'
            #         df.loc[idx, 'font'] = '22pt Arial'
            #     else:
            #         df.loc[idx, 'textFillStyle'] = 'black'
            #         df.loc[idx, 'font'] = '8pt Arial'

        if 'Open' in df.columns:
            df['Open'] = df['Open'].fillna(False) 
            df.loc[~(df['Open'] == True), 'text_str'] = ''

        self._data = df

    def render(self, parentObj):
        if 'text_fillStyle' not in self._data.columns:
            return

        for idx, r in self._data.iterrows():
            if (textObj := parentObj.children.get(f'TEXT_{idx}', None)) is not None:
                textObj.props['text_str'] = r['text_str']
                textObj.props['fillStyle'] = r['text_fillStyle']
                textObj.props['font'] = r['text_font']


# --------------------------------------------------
#    Main
# --------------------------------------------------
def start_threaded_automatic_update():
    """ example of how to run a periodic update from a different thread """
    def thread_worker():
        # init
        last_render_refresh_time = 0

        # loop forever
        while True:
            t = time.time()

            # refresh the data visually if needed
            if (t - last_render_refresh_time) > 0.1:
                for jsc in get_broadcast_jsclients('/'):

                    # refresh the render objects associated with the data
                    if 'ROOT_RENDER_OBJECT' in jsc.tag:
                        image_obj = jsc.tag['ROOT_RENDER_OBJECT'].children['img']                        
                        LAYER_CONTROLLER.render(image_obj)

                        f = JSDraw('ctx1', 'ctx2')
                        f.fillStyle = 'white'
                        f.clear()
                        jsc.tag['ROOT_RENDER_OBJECT'].render(f, t)
                        f.render(jsc)
                last_render_refresh_time = time.time()

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

    LAYER_CONTROLLER = LayerController(minimum_datasource_cooldown_period=0.1)

    # read the data coordinate file
    data_coord_file = os.path.join(os.path.dirname(__file__), args['data_coordinate_file'])
    df_data_coords = pd.read_csv(data_coord_file, index_col=0)
    lds_data_coords = LayerDataSource(name='data_coords', next_fire_time=None, initial_data=df_data_coords)
    lds_value = LDS_Example_Values()
    lds_open = LDS_Example_Open()
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
