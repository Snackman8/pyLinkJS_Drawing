# --------------------------------------------------
#    Imports
# --------------------------------------------------
import concurrent.futures
import datetime
import threading
import time
import traceback
import pandas as pd


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

    def get_datasource_status_messages(self):
        keys = list(self._layer_datasources.keys())
        status_html = ''
        for k in keys:
            status_html += self._status_message_for_datasource(self._layer_datasources[k])
        return status_html


    def render(self, parentObj):
        # notify renderers that data source has been updated
        for dr in self._layer_datarenderers.values():
            try:
                dr.render(parentObj)
            except:
                print(traceback.format_exc())

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
                        print(traceback.format_exc())
                    del futures[k]
                    print(ds.name, 'data ready')
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
                        print(traceback.format_exc())

                # one second frequency
                time.sleep(1)
