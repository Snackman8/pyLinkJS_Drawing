# --------------------------------------------------
#    Imports
# --------------------------------------------------
import pandas as pd
import random


# --------------------------------------------------
#    Globals
# --------------------------------------------------
# one copy of the data for all jsc to use
# single thread updater to keep access synchronous
DF_LIVE_DATA = pd.DataFrame()


# --------------------------------------------------
#    Data Functions
# --------------------------------------------------
def update_DF_LIVE_DATA_open_opentime():
    """ update the open and opentime fields in the DF_LIVE_DATA """

    # *****
    # this is fake code, replace with real code that would actually query a data source
    # *****

    if DF_LIVE_DATA.empty:
        return

    # for the purposes of fake code, loop through all the data names and randomly open or close 10%
    for _ in range(0, int(len(DF_LIVE_DATA) / 2) + 1):
        # randomly choose a data name, invert the open
        idx = random.choice(DF_LIVE_DATA.index)
        DF_LIVE_DATA.loc[idx, 'Open'] = not DF_LIVE_DATA.loc[idx, 'Open']
        DF_LIVE_DATA.loc[idx, 'OpenTime'] = pd.Timestamp.now()

    refresh_render_data()


def update_DF_LIVE_DATA_value():
    """ called to update the data from the data source """

    # *****
    # this is fake code, replace with real code that would actually query a data source
    # *****

    if DF_LIVE_DATA.empty:
        return

    # for the purposes of fake code, loop through all the data names and randomly open or close 10%
    for _ in range(0, int(len(DF_LIVE_DATA) / 10) + 1):
        # randomly choose a data name, invert the open
        idx = random.choice(DF_LIVE_DATA.index)
        DF_LIVE_DATA.loc[idx, 'PreviousValue'] = DF_LIVE_DATA.loc[idx, 'Value']
        DF_LIVE_DATA.loc[idx, 'Value'] = random.randint(0, 300)
        DF_LIVE_DATA.loc[idx, 'ChangeTime'] = pd.Timestamp.now()

    refresh_render_data()


# --------------------------------------------------
#    Functions
# --------------------------------------------------
def _init_data_point(df, name, value, is_open, open_time):
    """ intialize a data point """
    df.loc[name, 'Value'] = value
    df.loc[name, 'text_str'] = ''
    df.loc[name, 'textFillStyle'] = 'black'
    df.loc[name, 'font'] = '20px Arial'
    df.loc[name, 'radius'] = 10
    df.loc[name, 'fillStyle'] = 'rgba(0, 0, 0, 1)'
    df.loc[name, 'ChangeTime'] = pd.Timestamp.now()
    df.loc[name, 'PreviousValue'] = 0
    df.loc[name, 'Open'] = is_open
    df.loc[name, 'OpenTime'] = open_time


def init_data(scale, data_context):
    """
        Initialize the data

        Name|x|y|Value|text_str|textFillStyle|font|radius|fillStyle|ChangeTime|PreviousValue|Open|OpenTime
    """
    global DF_LIVE_DATA

    df = data_context['data_coordinates'].copy()
    for idx, _ in df.iterrows():
        _init_data_point(df, idx, random.randint(0, 300), is_open=random.choices([True, False], [0.5, 0.5])[0], open_time=pd.Timestamp.now())

    DF_LIVE_DATA = df


def get_data():
    return DF_LIVE_DATA.copy()

def refresh_render_data():
    """ refresh the visual aspects of the data
        will be called at a higher frequency than update_data """
    # sanity check
    # if DF_DATA is None:
    #     return None

    if DF_LIVE_DATA.empty:
        return

    # get the data
    df = DF_LIVE_DATA

    # update the text to show the value rounded to int
    df['text_str'] = df['Value'].astype('int').astype('str')

    # compute the radius and color of the circle
    df['radius'] = df.apply(lambda x: max(3, x['Value'] / 20.0), axis=1)
    df['fillStyle'] = 'rgba(0, 255, 0, 0.2)'
    df.loc[df['Value'] < 100, 'fillStyle'] = 'rgba(255, 0, 255, 0.2)'

    # recently changed data should have bigger text for 5 seconds
    t = pd.Timestamp.now()
    for idx, r in df.iterrows():
        if pd.Timedelta(t - r['ChangeTime']).seconds < 5:
            df.loc[idx, 'textFillStyle'] = 'black'
            df.loc[idx, 'font'] = '12pt Arial'
        else:
            df.loc[idx, 'textFillStyle'] = 'black'
            df.loc[idx, 'font'] = '8pt Arial'

    # closed should just show a small grey dot with no text
    df.loc[~(df['Open'] == True), 'text_str'] = ''
    df.loc[~(df['Open'] == True), 'radius'] = 2
    df.loc[~(df['Open'] == True), 'fillStyle'] = 'rgba(192, 192, 192, 0.5)'

    return df
