"""Demo pyLinkJS_Drawing application with synthetic datasources and layered renderers.

This example wires browser event callbacks to ``LayerApp``, simulates changing
data inputs, and renders circle/text overlays on top of a background drawing.
"""

# --------------------------------------------------
#    Imports
# --------------------------------------------------
import argparse
import datetime
import os
import random
import time
import logging
import pandas as pd
from pylinkjs.PyLinkJS import run_pylinkjs_app
from pyLinkJS_Drawing.drawingPlugin import pluginDrawing, CircleObject, RectObject, TextObject
from pyLinkJS_Drawing.layerController import LayerDataSource, LayerRenderer, LayerApp


# --------------------------------------------------
#    Globals
# --------------------------------------------------
LAYER_APP = None


# --------------------------------------------------
#    Event Handlers
# --------------------------------------------------
def onmouseup(jsc, x, y, button):
    """Dispatch a mouse-up event to the active layer application.

    Args:
        jsc: Active pyLinkJS client.
        x: World-space mouse x coordinate.
        y: World-space mouse y coordinate.
        button: Browser mouse button code.

    Returns:
        None.

    Note:
        - Delegates to ``LayerApp.on_mouseup`` for full behavior.
    """
    return LAYER_APP.on_mouseup(jsc, x, y, button)


def options_changed(jsc, *args):
    """Dispatch browser option changes to the active layer application.

    Args:
        jsc: Active pyLinkJS client.
        *args: Unused callback arguments.

    Returns:
        None.

    Note:
        - Delegates to ``LayerApp.on_options_changed``.
    """
    return LAYER_APP.on_options_changed(jsc)


def ready(jsc, *args):
    """Initialize demo state for a connected browser client.

    Args:
        jsc: Active pyLinkJS client.
        *args: Unused callback arguments.

    Returns:
        None.

    Note:
        - Uses fixed context names ``ctx_drawing`` and ``ctx_display``.
    """
    return LAYER_APP.on_ready(jsc, jsc.tag['background_file'], 'ctx_drawing', 'ctx_display')


def reconnect(jsc, *args):
    """Reinitialize demo state after client reconnect.

    Args:
        jsc: Active pyLinkJS client.
        *args: Unused callback arguments.

    Returns:
        None.

    Note:
        - Calls ``ready`` to rebuild per-client state after reconnect.
    """
    ready(jsc)


# --------------------------------------------------
#    Layer Implementation
# --------------------------------------------------
class LDS_Example_Values(LayerDataSource):
    """Example datasource that emits numeric value updates."""
    def __init__(self, cooldown_period=5):
        """Initialize the synthetic numeric-value datasource.

        Args:
            cooldown_period: Poll interval in seconds. Default is ``5``.

        Returns:
            None.

        Note:
            - See ``LayerDataSource.__init__`` for base datasource fields.
            - Calls base constructor with fixed datasource name
              ``'ExampleValues'``.
        """
        super().__init__(name='ExampleValues', cooldown_period=cooldown_period)

    @classmethod
    def data_fetch(cls):
        """Fetch synthetic numeric values for demo indices.

        Returns:
            Dataframe with value and timestamp columns.

        Note:
            - Implements ``LayerDataSource.data_fetch``.
            - Reads/writes ``Values.csv`` for simple persisted demo state.
        """
        time.sleep(1)
        # Keep example state persistent across refreshes.
        try:
            df = pd.read_csv('Values.csv', index_col=0)
        except:
            logging.warning('Values.csv not found or unreadable; creating seed dataframe.')
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
    """Example datasource that emits open/closed boolean states."""
    def __init__(self, cooldown_period=5):
        """Initialize the synthetic open/closed-state datasource.

        Args:
            cooldown_period: Poll interval in seconds. Default is ``5``.

        Returns:
            None.

        Note:
            - See ``LayerDataSource.__init__`` for base datasource fields.
            - Calls base constructor with fixed datasource name
              ``'ExampleOpen'``.
        """
        super().__init__(name='ExampleOpen', cooldown_period=cooldown_period)

    @classmethod
    def data_fetch(cls):
        """Fetch synthetic open/closed states for demo indices.

        Returns:
            Dataframe with boolean open/closed state values.

        Note:
            - Implements ``LayerDataSource.data_fetch``.
        """
        time.sleep(10)
        idx = []
        open_vals = []
        for _ in range(0, random.randint(12, 13)):
            idx.append(f'D-{random.randint(1,13)}')
            open_vals.append(random.choice([True, False]))
        df = pd.DataFrame(data={'Open': open_vals, 'index': idx}).drop_duplicates(subset='index', keep='last').set_index('index')
        return df


class LR_Example_Circle(LayerRenderer):
    """Example renderer for circle render objects."""

    def layer_init(self, parentObj):
        """Create circle render objects for each indexed demo point.

        Args:
            parentObj: Parent render object for circle children.

        Returns:
            None.

        Note:
            - Implements ``LayerRenderer.layer_init``. See base class docs for
              lifecycle details.
        """
        for idx, r in self._data.iterrows():
            circle_obj = CircleObject(name=f'CIRCLE_{idx}', x=r['x'], y=r['y'], radius=1, fillStyle='black', lineWidth=0.1, layer_name=self.name)
            parentObj.add_child(circle_obj)

    def get_options(self):
        """Return UI options used by this renderer.

        Returns:
            List of option descriptor dictionaries.

        Note:
            - Implements ``LayerRenderer.get_options``.
        """
        return [{'id': 'circle', 'text': 'Example Circle', 'type': 'Boolean', 'default_value': True}]

    def get_tooltip(self, tooltip_idx):
        """Return tooltip HTML for a selected point.

        Args:
            tooltip_idx: Index of selected point.

        Returns:
            HTML fragment string.

        Note:
            - Implements ``LayerRenderer.get_tooltip``.
        """
        return 'Radius: ' + str(self._data.loc[tooltip_idx].circle_radius) + '<br>'

    def render(self, parentObj, options):
        """Update circle visibility and styling from datasource state.

        Args:
            parentObj: Parent render object containing circle children.
            options: Runtime renderer options selected in UI.

        Returns:
            None.

        Note:
            - Implements ``LayerRenderer.render``. See base class docs for
              invocation timing.
        """
        # make a copy of the data
        df = self._data.copy()

        df['circle_radius'] = 0
        df['circle_fillStyle'] = 'rgba(0, 0, 0, 0)'

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

        visible = options['circle']

        for idx, r in df.iterrows():
            if (circleObj := parentObj.children.get(f'CIRCLE_{idx}', None)) is not None:
                circleObj.props['visible'] = visible
                circleObj.props['radius'] = r['circle_radius']
                circleObj.props['fillStyle'] = r['circle_fillStyle']


class LR_Example_Text(LayerRenderer):
    """Example renderer for text render objects and click-hit regions."""

    def layer_init(self, parentObj):
        """Create click-hit boxes and text render objects for each point.

        Args:
            parentObj: Parent render object for text-related children.

        Returns:
            None.

        Note:
            - Implements ``LayerRenderer.layer_init``. See base class docs for
              lifecycle details.
        """
        click_width = 15
        click_height = 12
        for idx, r in self._data.iterrows():
            click_obj = RectObject(name=f'CLICK_{idx}', x=r['x'] - click_width / 2, y=r['y']- click_height / 2, width=click_width, height=click_height, strokeStyle='rgba(0, 0, 0, 0)', fillStyle='rgba(0, 0, 0, 0)', clickable=True, layer_name=self.name, idx=idx)
            text_obj = TextObject(name=f'TEXT_{idx}', x=r['x'], y=r['y'], text_str='?', lineWidth=0.1, fillStyle='black', font='8pt Arial', textAlign='center', textBaseline='middle', layer_name=self.name, idx=idx)
            parentObj.add_child(click_obj)
            parentObj.add_child(text_obj)

    def get_options(self):
        """Return UI options used by this renderer.

        Returns:
            List of option descriptor dictionaries.

        Note:
            - Implements ``LayerRenderer.get_options``.
        """
        return [{'id': 'text', 'text': 'Example Text', 'type': 'Boolean', 'default_value': True},
                {'id': 'always_red', 'text': 'Always Red', 'type': 'Boolean', 'default_value': False}]

    def get_tooltip(self, tooltip_idx):
        """Return tooltip HTML for a selected point.

        Args:
            tooltip_idx: Index of selected point.

        Returns:
            HTML fragment string.

        Note:
            - Implements ``LayerRenderer.get_tooltip``.
        """
        return tooltip_idx + '<br>Value: ' + str(self._data.loc[tooltip_idx].Value) + '<br>TimeStamp: ' + str(self._data.loc[tooltip_idx].Value_ts) + '<br>'

    def render(self, parentObj, options):
        """Update text visibility/content/styling from datasource state.

        Args:
            parentObj: Parent render object containing text children.
            options: Runtime renderer options selected in UI.

        Returns:
            None.

        Note:
            - Implements ``LayerRenderer.render``. See base class docs for
              invocation timing.
        """
        # make a copy of the data
        df = self._data.copy()

        # set render properties
        df['text_fillStyle'] = 'black'
        df['text_font'] = '8pt Arial'
        df['text_str'] = '?'

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

                if options['always_red']:
                    df.loc[idx, 'text_fillStyle'] = 'red'

        if 'Open' in df.columns:
            df['Open'] = df['Open'].fillna(False)
            df.loc[~(df['Open'] == True), 'text_str'] = ''


        visible = options['text']

        for idx, r in df.iterrows():
            if (textObj := parentObj.children.get(f'TEXT_{idx}', None)) is not None:
                textObj.props['visible'] = visible
                textObj.props['text_str'] = r['text_str']
                textObj.props['fillStyle'] = r['text_fillStyle']
                textObj.props['font'] = r['text_font']


# --------------------------------------------------
#    Main
# --------------------------------------------------
def main(args):
    """Build demo layers and launch the pyLinkJS application.

    Args:
        args: Parsed CLI argument mapping.

    Returns:
        None.

    Note:
        - Builds two datasources and two renderers, then starts ``LayerApp``.
    """
    # globals
    global LAYER_APP

    # data_coords
    data_coord_file = os.path.join(os.path.dirname(__file__), args['data_coordinate_file'])
    df_data_coords = pd.read_csv(data_coord_file, index_col=0)
    lds_data_coords = LayerDataSource(name='data_coords', next_fire_time=None, initial_data=df_data_coords)
    # Example Values
    lds_value = LDS_Example_Values(cooldown_period=1)
    # Example Open
    lds_open = LDS_Example_Open(cooldown_period=1)

    # text
    lr_text = LR_Example_Text(name='text', starting_data_dict={'data_coords': df_data_coords}, subscribed_datasources=[lds_data_coords.name, lds_value.name, lds_open.name] )
    # circle
    lr_circle = LR_Example_Circle(name='circle', starting_data_dict={'data_coords': df_data_coords}, subscribed_datasources=[lds_data_coords.name, lds_value.name, lds_open.name] )

    # initialize the LAYER_APP
    LAYER_APP = LayerApp(data_sources=[lds_data_coords, lds_value, lds_open], renderers=[lr_text, lr_circle])
    LAYER_APP.start()

    # initialize the app
    drawing_plugin = pluginDrawing('ctx_drawing', 'ctx_display')
    run_pylinkjs_app(default_html='pyLinkJS_Drawing_example.html', extra_settings={'background_file': args['background_file'], 'data_coordinates_file': args['data_coordinate_file']}, plugins=[drawing_plugin])


if __name__ == '__main__':
    # start the thread and the app
    logging.basicConfig(level=logging.DEBUG, format='%(relativeCreated)6d %(threadName)s %(message)s')

    # parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--background_file', help='file location of the background image', default='floor_plan.svg')
    parser.add_argument('--data_coordinate_file', help='file location of the data coordinates', default='data_coords.csv')
    args = parser.parse_args()
    args = vars(args)

    # run the main
    main(args)
