# --------------------------------------------------
#    Imports
# --------------------------------------------------
import datetime
import queue
from multiprocessing import Queue, Process
import random
import threading
import time
import traceback
import pandas as pd
from pyLinkJS_Drawing.drawingPlugin import CircleObject, TextObject


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
        
        # success!
        return df

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
        raise NotImplemented()

    def render(self, parentObj):
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

    def render(self, parentObj):
        # notify renderers that data source has been updated
        for dr in self._layer_datarenderers.values():
            try:
                dr.render(parentObj)
            except:
                print(traceback.format_exc())        

    def _thread_worker(self):
        """ thread worker, coordinate data fetches """

        processes = {}
        
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
                    
                    # add this process to the processes
                    q = Queue()
                    p = Process(target=LayerController._mp_wrapper, args=(ds.__class__.data_fetch, (), {}, q))
                    processes[ds.name] = {'queue': q, 'process': p}
                    p.start()

            # check processes for completion
            dirty_renderers = set()
            for k in list(processes.keys()):
                process_info = processes[k]
                ds = self._layer_datasources[k]
                # check if the data is ready
                try:
                    # check if data is ready
                    ds.set_data(process_info['queue'].get_nowait())
                    ds.next_fire_time = ds.data_last_fetch_time + datetime.timedelta(seconds=max(ds.cooldown_period, self.minimum_datasource_cooldown_period))                    

                    # notify renderers that the data has changed
                    for dr in self._layer_datarenderers.values():
                        if ds.name in dr.subscribed_datasources:
                            dirty_renderers.add(dr.name)
                except queue.Empty:
                    pass

            # update dirty renderers
            for name in list(dirty_renderers):
                dr = self._layer_datarenderers[name]
                data_dict = {}
                for dn in dr.subscribed_datasources:
                    data_dict[dn] = self._layer_datasources[dn].data
                try:
                    dr.on_data_changed(data_dict)
                except:
                    print(traceback.format_exc())

            # one second frequency
            time.sleep(1)
