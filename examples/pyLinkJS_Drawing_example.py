# --------------------------------------------------
#    Imports
# --------------------------------------------------
import argparse
import threading
import logging
import pandas as pd
from pylinkjs.PyLinkJS import run_pylinkjs_app, get_broadcast_jsclients
from pyLinkJS_Drawing.drawingPlugin import *
try:
    from .business_logic import init_data, refresh_render_data, update_DF_LIVE_DATA_open_opentime, update_DF_LIVE_DATA_value, get_data
except:
    from business_logic import init_data, refresh_render_data, update_DF_LIVE_DATA_open_opentime, update_DF_LIVE_DATA_value, get_data


# --------------------------------------------------
#    Globals
# --------------------------------------------------
DATA_CLICK_PREFIX = 'H'
DATA_CLICK_INDEX = 9


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

    # read the data coordinate file
    data_coord_file = os.path.join(os.path.dirname(__file__), jsc.tag['data_coordinates_file'])
    df_data_coords = pd.read_csv(data_coord_file, index_col=0)
    jsc.tag['data_context'] = {'data_coordinates': df_data_coords}

    # init the data
    init_data(1.0, jsc.tag['data_context'])

    # create the background
    root_obj = RectObject(flightplan=None, x=0, y=0, width=canvas_width, height=canvas_height, strokeStyle='rgba(0, 0, 0, 0)', fillStyle='rgba(0, 0, 0, 0)', clickable=False)

    # create the background
    image_obj = ImageObject(name='img', flightplan=None, x=0, y=0, width=img_width, height=img_height, image_name='img_floor_plan', filter_str='opacity(0.2)')
    root_obj.add_child(image_obj)

    # create the data text
    df = get_data()
    for idx, r in df.iterrows():
        text_obj = TextObject(name=f'TEXT_{idx}', x=r['x'], y=r['y'], text_str='?', lineWidth=0.1, fillStyle=r['textFillStyle'], font=r['font'], textAlign='center', textBaseline='middle')
        circle_obj = CircleObject(name=f'CIRCLE_{idx}', x=r['x'], y=r['y'], radius=r['radius'], fillStyle=r['fillStyle'], lineWidth=0.1)
        image_obj.add_child(circle_obj)
        image_obj.add_child(text_obj)

    jsc.tag['ROOT_RENDER_OBJECT'] = root_obj

    # render
    f.render(jsc)


# --------------------------------------------------
#    Main
# --------------------------------------------------
def start_threaded_automatic_update():
    """ example of how to run a periodic update from a different thread """
    def thread_worker():
        # init
        last_data_refresh_time = 0
        last_render_refresh_time = 0

        # loop forever
        while True:
            t = time.time()

            # update the data if needed
            if (t - last_data_refresh_time) > 10:
                # update the data every 30 seconds
                update_DF_LIVE_DATA_open_opentime()
                update_DF_LIVE_DATA_value()
                last_data_refresh_time = time.time()
                last_render_refresh_time = last_data_refresh_time

            # refresh the data visually if needed
            if (t - last_render_refresh_time) > 0.1:
                refresh_render_data()
                last_render_refresh_time = time.time()
                df = get_data()

                for jsc in get_broadcast_jsclients('/'):

                    # refresh the render objects associated with the data
                    if 'ROOT_RENDER_OBJECT' in jsc.tag:
                        image_obj = jsc.tag['ROOT_RENDER_OBJECT'].children['img']
                        for idx, r in df.iterrows():
                            if (textObj := image_obj.children.get(f'TEXT_{idx}', None)) is not None:
                                textObj.props['text_str'] = r['text_str']
                                textObj.props['fillStyle'] = r['textFillStyle']
                                textObj.props['font'] = r['font']
                            if (circleObj := image_obj.children.get(f'CIRCLE_{idx}', None)) is not None:
                                circleObj.props['radius'] = r['radius']
                                circleObj.props['fillStyle'] = r['fillStyle']

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

    # init the google oauth2 plugin
    drawing_plugin = pluginDrawing('ctx1', 'ctx2')

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
