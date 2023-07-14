""" Plugin for HTML5 Canvas Drawing Applications """

# --------------------------------------------------
#    Imports
# --------------------------------------------------
import os
import math
import time
import uuid
from copy import deepcopy
from functools import partial


# --------------------------------------------------
#    Classes
# --------------------------------------------------
class JSDraw(object):
    # drawing functions defined in pylinkjsDraw
    DRAWING_FUNCS = {
        'ellipse': ['x', 'y', 'radiusX', 'radiusY', 'rotation', 'startAngle', 'endAngle', 'counterclockwise'],
        'image': ['image_name', 'x', 'y', 'w', 'h', 'filter_str'],
        'line': ['x1', 'y1', 'x2', 'y2'],
        'roundRect': ['x', 'y', 'width', 'height', 'radii'],
        'text': ['x', 'y', 'text_str'],}

    # standard canvas drawing properties which are strings
    DRAWING_PROPS_STR = {
        'fillStyle': None,
        'font': None,
        'lineWidth': None,
        'strokeStyle': None,
        'strokeStyleObj': None,
        'textAlign': None,
        'textBaseline': None,
        'textBaseline': None,}

    # standard canvas drawing properties which are not strings
    DRAWING_PROPS = {
        'lineWidth': None,
        'fillStyleObj': None,
        }

    # union of all the canvas drawing properties
    ALL_DRAWING_PROPS = DRAWING_PROPS | DRAWING_PROPS_STR

    def __init__(self, canvas_context_working_name, canvas_context_target_name):
        """ init

            Args:
                canvas_context_working_name - name of the working canvas context for drawing
                canvas_context_target_name - name of the target canvas which the working canvas
                                             will be copied to for double buffering
        """
        self.__dict__['_canvas_context_working_name'] = canvas_context_working_name
        self.__dict__['_canvas_context_target_name'] = canvas_context_target_name
        self.__dict__['_commands'] = []

    def __getattr__(self, key):
        """ handler for undefined attributes.  Delegate to reading a canvas drawing attribute

            Args:
                key - name of the attribute to read

            Returns:
                the value of the attribute
        """
        if key in self.ALL_DRAWING_PROPS:
            return self.DRAWING_PROPS[key]
        if key in self.DRAWING_FUNCS:
            return partial(self._proxy_func_handler, key, self.DRAWING_FUNCS[key])

        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{key}")

    def __setattr__(self, key, value):
        """ handler for undefined attributes.  Delegate to writing a canvas drawing attribute
            TODO: we can optimize this in the future by not setting properties which have the correct value already

            Args:
                key - name of the attribute to write
                value - new value for the attribute
        """
        if key in self.ALL_DRAWING_PROPS:
            # save the value
            if key in self.DRAWING_PROPS:
                self.DRAWING_PROPS[key] = value
            else:
                self.DRAWING_PROPS_STR[key] = value

            # properties that end with Obj are handled differently, they are written as the object name
            # without double quotes since we are passing the actual variable and not a string
            if key.endswith('Obj'):
                if key[:-3] in self.DRAWING_PROPS:
                    self.DRAWING_PROPS[key[:-3]] = None
            if (key + 'Obj') in self.DRAWING_PROPS:
                self.DRAWING_PROPS[key + 'Obj'] = None

            kwargs = {}
            kwargs['context_name'] = self._canvas_context_working_name
            kwargs['prop_name'] = key
            kwargs['value'] = value

            # properties that end with Obj are handled differently, they are written as the object name
            # without double quotes since we are passing the actual variable and not a string
            if key.endswith('Obj'):
                kwargs['prop_name'] = key[:-3]
                # add the command to the command queue which willb e sent to javascript
                self._commands.append(['{context_name}.{prop_name} = {value};', kwargs])
            else:
                if key in self.DRAWING_PROPS:
                    # add the command to the command queue which willb e sent to javascript
                    self._commands.append(['{context_name}.{prop_name} = {value};', kwargs])
                else:
                    # add the command to the command queue which willb e sent to javascript
                    self._commands.append(['{context_name}.{prop_name} = \'{value}\';', kwargs])
        else:
            return super().__setattr__(key, value)

    def _proxy_func_handler(self, func_name, arg_names, *args, **kwargs):
        """ create a function call command and place into the command queue which will be batched
            and sent to the browser to render javascript canvas

            Args:
                func_name - name of the function
                arg_names - name of the arguments
                *args - argument values
                **kwargs - keywrod argument names and values
        """
        # convert the args into kwargs
        for i, a in enumerate(args):
            kwargs[arg_names[i]] = a

        # inject the canvas name
        kwargs['context_name'] = self._canvas_context_working_name

        # convert to a named parameter list, i.e. "({x}, {y})"
        params = ['({context_name}']
        for x in arg_names:
            if x.endswith('_str'):
                params.append(f"'{{{x}}}'")
            else:
                params.append(f'{{{x}}}')
        params[-1] = params[-1] + ');'
        named_param_string = ','.join(params)

        # save the context
        self.context_save()

        # set the override properties for this function call
        for k in list(kwargs.keys()):
            if k in self.DRAWING_PROPS:
                self.__setattr__(k, kwargs[k])
                del kwargs[k]

        # issue the actual drawing command
        self._commands.append([f'draw_{func_name}{named_param_string}', kwargs])

        # restore the context
        self.context_restore()

    def clear(self):
        """ clear the canvas """
        self._commands.append(['clear({context_name});', {'context_name': self._canvas_context_working_name}])

    def clear_renderer(self):
        """ clear the renderer history.  A scene is built up of multiple commands rendered in order.  The deleted all of the commands """
        self._commands = []

    def context_restore(self):
        """ restore the canvas context """
        self._commands.append(['{context_name}.restore();', {'context_name': self._canvas_context_working_name}])

    def context_save(self):
        """ save the canvas context """
        self._commands.append(['{context_name}.save();', {'context_name': self._canvas_context_working_name}])

    def create_image(self, name, image_src):
        """ create an image object

            Args:
                name - name of the new image
                image_src - url to the image

            Returns:
                None
        """
        kwargs = {'name': name, 'image_src': image_src}
        self._commands.append(['{name} = new Image(100, 100);', kwargs])
        self._commands.append(["{name}.src = '{image_src}';", kwargs])

    def gradient_radial(self, name, x0, y0, r0, x1, y1, r1, color_stops):
        """ create a radial gradient

            Args:
                name - name of the new gradient
                x0, y0, r0 - center and radius of the first color
                x1, y1, r1 - center and radius of the second color
                color_stops - list of 2 colors

            Returns:
                None
        """
        kwargs = {'context_name': self._canvas_context_working_name, 'name': name, 'x0': x0, 'y0': y0, 'r0': r0, 'x1': x1, 'y1': y1, 'r1': r1}
        self._commands.append(['{name} = {context_name}.createRadialGradient({x0}, {y0}, {r0}, {x1}, {y1}, {r1});', kwargs])
        for cs in color_stops:
            self._commands.append(['{name}.addColorStop({r}, \'{c}\');', {'name': name, 'r': cs[0], 'c': cs[1]}])

    def render(self, jsc, clear=True):
        """ render the frame

            Args:
                jsc - javascript client containing the canvas contexts to render to
                clear - if True, automatically clear the rendered command queue after render
                        The image will be sent to javascript and rendered, and the python render queue will
                        be cleared, ready to construct the next frame

            Returns:
                None
        """
        # build a javascript string to render
        js_list = []
        for c in self._commands:
            try:
                js_list.append(c[0].format(**c[1]))
            except Exception as e:
                raise(e)
        js_list.append(f'flip({self._canvas_context_working_name}.canvas, {self._canvas_context_target_name});')
        js = '\n'.join(js_list)
        js = js.replace('\n', '\\n')
        js = f'render("{js}");'
        jsc.eval_js_code(js, blocking=True)
        if clear:
            self.clear_renderer()


# --------------------------------------------------
#    Tweening Base Classes
# --------------------------------------------------
class FlightPlan():
    """ to start the flight plan right now set the start_time to now
        to start the flight plan at a future time set the start_time to the future time
        to stop the flight plan at a future time, set the duration to the length of the flight
        to pause a flight plan midflight, call the pause function
        to resume a paused flight, call the resume function
    """
    def __init__(self, decision_handler=[], duration=None, name=None):
        """ Initialize the flight plan

            Args:
                decision_handler - list of funtions that will be called in order to adjust the flight plan while in flight
                duration - maximum duration of the flight
                name - name of the flght plan
        """
        # save the name
        self.name = name

        # properties which are reversible need to be stored in the forward properties dictionary
        self.fprops = {}
        self.fprops['start_time'] = None
        self.fprops['pause_time'] = None
        self.fprops['duration'] = duration

        # working properties are stored in props
        self.props = {}

        # vectors are pixels / sec
        self.decision_handler = decision_handler

    def _calculate_time_from_zero(self, t):
        """ calculates the working time from zero

            If the flight plan has not started yet, then working time will be zero
            if the flight plan has ended, the working time will be capped by maximum flight plan
            If the flight is paused, the working timm will be the start of the paused time

            Args:
                t - actual time

            Returns:
                working time
        """
        try:
            # if the flight plan is paused, return the time offset when it was paused
            if self.props['pause_time'] is not None:
                return self.props['pause_time'] - self.props['start_time']

            # if the flight plan has no start time or the time is before the start time, return 0
            if self.props['start_time'] is None or t <= self.props['start_time']:
                return 0

            # if the flight plan has no duration, return the elapsed flgiht time
            tdelta = t - self.props['start_time']
            if self.props['duration'] is None:
                return tdelta

            # return either the elapsed flight time or the duration, whichever is less
            return min(tdelta, self.props['duration'])
        except:
            print('AAA')
            raise Exception()

    def _set_default_prop_list(self, key, val):
        self.fprops[key] = list(self.fprops.get(key, val))

    def calculate_position(self, renderObj, t):
        # calculate the position without parent offset
        tz = self._calculate_time_from_zero(t)
        positions = self.custom_calculate_position(tz)

        # scale our positions only if we have a parent
        if renderObj.parent is not None:
            positions = [x * renderObj.props['scale'] for x in positions]

        # no parent, just return the position
        if renderObj.parent is None:
            return positions

        # there is a parent, so add the parent's position
        ppos = renderObj.parent.flightplan.calculate_position(renderObj.parent, t)
        retval = []
        for i in range(0, len(ppos)):
            retval.append(positions[i] + ppos[i])

        return retval

    def custom_calculate_position(self, tz):
        raise NotImplementedError

    def get_positions(self, renderObj, t):
        # check the decision handler
        if self.decision_handler:
            for dh_func in self.decision_handler:
                if callable(dh_func):
                    dh_func(renderObj, self, t)
                elif hasattr(dh_func, 'decide'):
                    dh_func.decide(renderObj, self, t)

        return self.calculate_position(renderObj, t)

    def is_active(self, t):
        if self.props['start_time'] is None or t <= self.props['start_time']:
            return False

        if self.props['end_time'] is None and t <= self.props['end_time']:
            return True

        return False

    def pause(self):
        self.props['pause_time'] = time.time()

    def resume(self):
        delta_time = time.time() - self.props['pause_time']
        self.props['start_time'] += delta_time
        self.props['end_time'] += delta_time
        self.props['pause_time'] = None

    def start_forward_flight(self, start_time=-99999999):
        """ setup the props for a forward flight from start to end """
        self.props = deepcopy(self.fprops)
        if start_time == -99999999:
            start_time = time.time()
        self.props['start_time'] = start_time

    def start_reverse_flight(self, start_time=-99999999):
        """ setup the props for a reverse flight from start to end """
        raise NotImplementedError


class RenderObject():
    def __init__(self, flightplan=None, **kwargs):
        # defaults
        kwargs['name'] = kwargs.get('name', f'{uuid.uuid4()}')
        kwargs['fillStyle'] = kwargs.get('fillStyle', 'white')
        kwargs['glow'] = kwargs.get('glow', False)
        kwargs['glow_attenuation'] = kwargs.get('glow_attenuation', [0.33, 0.33, 0.33, 0.03])
        kwargs['glow_width'] = kwargs.get('glow_width', 40)
        kwargs['clickable'] = kwargs.get('clickable', True)
        kwargs['scale'] = kwargs.get('scale', 1)
        kwargs['strokeStyle'] = kwargs.get('strokeStyle', 'black')
        kwargs['visible'] = kwargs.get('visible', True)

        # fix fillStyle
        if kwargs['fillStyle'] is None:
            kwargs['fillStyle'] = 'rgba(0, 0, 0, 0)'

        # children and parent
        self.children = {}
        self.parent = None

        # save the flightplan
        self.flightplan = flightplan

        # save the properties
        self.props = kwargs.copy()

        # clean the properties if Obj and non-Obj exist
        for k in list(self.props.keys()):
            if k.endswith('Obj'):
                if k[:-3] in self.props:
                    del self.props[k[:-3]]

    def _point_in_obj_children(self, x, y, t):
        # check the children of this renderobject for a point inside of them
        #    return the first child render object which has a hit
        for c in self.children.values():
            ro_hit = c.point_in_obj(x, y, t)
            if ro_hit is not None:
                return ro_hit

        return None

    def add_child(self, childobj):
        self.children[childobj.props['name']] = childobj
        childobj.parent = self

    @classmethod
    def color_calculate_glow(cls, rgba_string, glow_attenuation):
        color_glow = cls.color_decode(rgba_string)
        for i in range(0, 4):
            color_glow[i] = color_glow[i] * glow_attenuation[i]
        color_glow = cls.color_encode(color_glow)
        return color_glow

    @classmethod
    def color_decode(cls, rgba_string):
        try:
            rgba_string = rgba_string.strip()
            if rgba_string.startswith('rgba(') and rgba_string.endswith(')'):
                rgba_string = rgba_string[5:-1]
                retval  = [float(x) for x in rgba_string.split(',')]
                return retval
            else:
                return [0, 0, 0, 0]
        except:
            return [0, 0, 0, 0]

    @classmethod
    def color_encode(cls, rgba_list):
        return f'rgba({rgba_list[0]}, {rgba_list[1]}, {rgba_list[2]}, {rgba_list[3]})'

    def customrender(self, f, t):
        """ default custom renderer of a circle """
        try:
            positions = self.flightplan.get_positions(self, t)
        except:
            positions = [0, 0]
        f.circle(x=positions[0], y=positions[1], r=20 * self.props['scale'], fillStyle='white', strokeStyle='red')

    def draw_glow(self, partial_func, **kwargs):
        # render the glow if needed
        if self.props.get('glow', False):
            # calculate glow color
            color_glow = self.color_calculate_glow(
                kwargs.get('strokeStyle', self.props.get('strokeStyle', 'rgba(0,0,0,0)')),
                kwargs.get('glow_attenuation', self.props['glow_attenuation']))

            # draw the glow liens
            for i in range(1, kwargs.get('glow_width', self.props.get('glow_width'))):
                partial_func(lineWidth=i, strokeStyle=color_glow)

        # draw the hard border
        partial_func()

    def prerender(self, f, t):
        """ save the context state and then set the default drawing properties for this render object """
        # apply the properties globally
        f.context_save()
        for k in self.props:
            if k in JSDraw.ALL_DRAWING_PROPS:
                setattr(f, k, self.props[k])

    def postrender(self, f, t):
        """ restore the context state """
        f.context_restore()

    def render(self, f, t):
        """ drawing props set on the RenderObject are the defaults when rendering """
        if not self.props['visible']:
            return

        # call prerender
        self.prerender(f, t)

        # render the children
        for v in list(self.children.values()):
            v.render(f, t)

        # call customrender
        self.customrender(f, t)

        # call postrender
        self.postrender(f, t)

    def set_scale(self, new_scale):
        self.props['scale'] = new_scale
        for c in self.children.values():
            c.set_scale(new_scale)


# --------------------------------------------------
#    Implementation Classes
# --------------------------------------------------
class BounceHandler():
    def __init__(self, x1, y1, r1, x2, y2, r2):
        self.x1 = x1
        self.y1 = y1
        self.r1 = r1
        self.x2 = x2
        self.y2 = y2
        self.r2 = r2

    def decide(self, renderObj, fp, t):
        # abort if not active
        if not fp.is_active(t):
            return

        # bounce
        positions = fp.calculate_position(renderObj, t)

        reset = False
        if positions[0] < (self.x1 + positions[2]):
            if fp.vector[0] < 0:
                reset = True
                fp.vector[0] = -fp.vector[0]

        if positions[0] > (self.x2 - positions[2]):
            if fp.vector[0] > 0:
                reset = True
                fp.vector[0] = -fp.vector[0]

        if positions[1] < (self.y1 + positions[2]):
            if fp.vector[1] < 0:
                reset = True
                fp.vector[1] = -fp.vector[1]

        if positions[1] > (self.y2 - positions[2]):
            if fp.vector[1] > 0:
                reset = True
                fp.vector[1] = -fp.vector[1]

        if positions[2] < self.r1:
            if fp.vector[2] < 0:
                reset = True
                fp.vector[2] = -fp.vector[2]

        if positions[2] > self.r2:
            if fp.vector[2] > 0:
                reset = True
                fp.vector[2] = -fp.vector[2]

        if reset:
            fp.start_time = time.time()
            fp.start_position = positions


# --------------------------------------------------
#    Render Objects
# --------------------------------------------------
class EllipseObject(RenderObject):
    """ x, y, radiusX, radiusY, rotation, start_angle, end_angle"""
    def __init__(self, flightplan=None, **kwargs):
        kwargs['radiusX'] = kwargs.get('radiusX', 100)
        kwargs['radiusY'] = kwargs.get('radiusY', 50)
        kwargs['rotation'] = kwargs.get('rotation', 0)
        kwargs['startAngle'] = kwargs.get('start_angle', 0)
        kwargs['endAngle'] = kwargs.get('end_angle', math.pi*2)
        kwargs['counterclockwise'] = kwargs.get('counterclockwise', 0)
        if flightplan is None:
            if 'x' in kwargs and 'y' in kwargs:
                flightplan = StaticFlightPlan(start_position=(kwargs['x'], kwargs['y']))
            else:
                raise Exception('Either flightplan or x,y must be passed in')
        super().__init__(flightplan=flightplan, **kwargs)

    def customrender(self, f, t):
        if self.flightplan:
            # calculate new position
            positions = self.flightplan.get_positions(self, t)
            f.ellipse(positions[0], positions[1], self.props['radiusX'] * self.props['scale'], self.props['radiusY'] * self.props['scale'],
                      self.props['rotation'], self.props['startAngle'], self.props['endAngle'], self.props['counterclockwise'])

    def point_in_obj(self, x, y, t):
        if self.flightplan:
            positions = self.flightplan.get_positions(self, t)
            dx = (x - positions[0]) / (self.props['radiusX'] * self.props['scale'])
            dy = (y - positions[1]) / (self.props['radiusY'] * self.props['scale'])
            if (dx * dx + dy * dy - 1) <= 0:
                return self

        return self._point_in_obj_children(x, y, t)


class CircleObject(EllipseObject):
    """ x, y, radius """
    def __init__(self, flightplan=None, **kwargs):
        kwargs['radius'] = kwargs.get('radius', 100)
        super().__init__(flightplan=flightplan, **kwargs)

    def customrender(self, f, t):
        self.props['radiusX'] = self.props['radius']
        self.props['radiusY'] = self.props['radius']
        super().customrender(f, t)


class RoundRectObject(RenderObject):
    """ x, y, width, height, radii """
    def __init__(self, flightplan=None, **kwargs):
        kwargs['width'] = kwargs.get('width', 200)
        kwargs['height'] = kwargs.get('height', 10)
        kwargs['radii'] = kwargs.get('radii', [20, 20, 40, 40])
        if flightplan is None:
            if 'x' in kwargs and 'y' in kwargs:
                flightplan = StaticFlightPlan(start_position=(kwargs['x'], kwargs['y']))
            else:
                raise Exception('Either flightplan or x,y must be passed in')
        super().__init__(flightplan=flightplan, **kwargs)

    def customrender(self, f, t):
        if self.flightplan:
            # calculate new position
            positions = self.flightplan.get_positions(self, t)
            f.roundRect(positions[0], positions[1], self.props['width'] * self.props['scale'], self.props['height'] * self.props['scale'], self.props['radii'])

    def point_in_obj(self, x, y, t):
        if self.flightplan:
            positions = self.flightplan.get_positions(self, t)
            x = x - positions[0]
            y = y - positions[1]
            if (x >= 0) and (x < self.props['width'] * self.props['scale']) and (y >= 0) and (y < self.props['height'] * self.props['scale']):
                return self

        return self._point_in_obj_children(x, y, t)


class ImageObject(RoundRectObject):
    """ x, y, radius """
    def __init__(self, flightplan=None, **kwargs):
        kwargs['image_name'] = kwargs.get('image_name', None)
        kwargs['width'] = kwargs.get('width', None)
        kwargs['height'] = kwargs.get('height', None)
        kwargs['filter_str'] = kwargs.get('filter_str', '')
        super().__init__(flightplan=flightplan, **kwargs)

    def customrender(self, f, t):
        if self.flightplan:
            # calculate new position
            positions = self.flightplan.get_positions(self, t)
#            f.roundRect(positions[0], positions[1], self.props['width'] * self.props['scale'], self.props['height'] * self.props['scale'], 0, strokeStyle='red', fillStyle='rgba(0,0,0,0)')
            if self.props['image_name'] is not None:
                f.image(self.props['image_name'], positions[0], positions[1], self.props['width'], self.props['height'], filter_str=self.props['filter_str'])

    def point_in_obj(self, x, y, t):
        if self.flightplan:
            positions = self.flightplan.get_positions(self, t)
            x = x - positions[0]
            y = y - positions[1]
            if (x >= 0) and (x < self.props['width'] * self.props['scale']) and (y >= 0) and (y < self.props['height'] * self.props['scale']):
                return self

        return self._point_in_obj_children(x, y, t)


class RectObject(RoundRectObject):
    """ x, y, radius """
    def __init__(self, flightplan=None, **kwargs):
        kwargs['radii'] = [0, 0, 0, 0]
        super().__init__(flightplan=flightplan, **kwargs)


class TextObject(RenderObject):
    """ x, y, text_str
        fillStyle, strokeStyle
    """
    def __init__(self, flightplan=None, **kwargs):
        kwargs['text_str'] = kwargs.get('text_str', 'ABCD')
        if flightplan is None:
            if 'x' in kwargs and 'y' in kwargs:
                flightplan = StaticFlightPlan(start_position=(kwargs['x'], kwargs['y']))
            else:
                raise Exception('Either flightplan or x,y must be passed in')
        super().__init__(flightplan=flightplan, **kwargs)

    def customrender(self, f, t):
        if self.flightplan:
            # calculate new position
            positions = self.flightplan.get_positions(self, t)
            f.text(text_str=self.props['text_str'], x=positions[0], y=positions[1], fillStyle=self.props['fillStyle'])

    def point_in_obj(self, x, y, t):
        return self._point_in_obj_children(x, y, t)


# --------------------------------------------------
#    Flight Plans
# --------------------------------------------------
class OrbitFlightPlan(FlightPlan):
    def __init__(self, decision_handler=[], duration=None, name=None, **kwargs):
        """
            center - (x, y) center of orbit
            vector - (degrees / sec, orbit radius / sec, node radius / sec)
            start_position - (angle in degrees, orbit radius, node radius)
        """
        # call super
        super().__init__(decision_handler=decision_handler, duration=duration, name=name)

        # additional fprops
        self.fprops.update(kwargs.copy())
        self._set_default_prop_list('center', [0,0])
        self._set_default_prop_list('vector_start', [0,0])
        self._set_default_prop_list('vector', [0,0])

        self.start_forward_flight(start_time=None)

    def custom_calculate_position(self, tz):
        # angle
        angle = (self.props['vector_start'][0] + self.props['vector'][0] * tz) % 360
        radius = (self.props['vector_start'][1] + self.props['vector'][1] * tz)

        positions = []
        for i in range(0, len(self.props['vector'])):
            if i == 0:
                positions.append(self.props['center'][0] + math.cos(angle / 360.0 * 2 * math.pi) * radius)
            elif i == 1:
                positions.append(self.props['center'][1] + math.sin(angle / 360.0 * 2 * math.pi) * radius)
            else:
                self.props['vector_start'][i] + self.props['vector'][i] * tz

        return positions

    def start_reverse_flight(self, start_time=-99999999):
        """ setup the props for a reverse flight from start to end """
        tz = self._calculate_time_from_zero(time.time())
        self.props = deepcopy(self.fprops)

        for i in range (0, len(self.props['vector_start'])):
            self.props['vector_start'][i] = self.props['vector_start'][i] + self.props['vector'][i] * tz

        self.props['vector'] = [-x for x in self.props['vector']]

        if start_time == -99999999:
            start_time = time.time()

        self.props['start_time'] = start_time


class StaticFlightPlan(FlightPlan):
    def __init__(self, decision_handler=None, **kwargs):
        # call super
        super().__init__(decision_handler=decision_handler)

        # additional fprops
        self.fprops.update(kwargs.copy())
        self._set_default_prop_list('start_position', [0, 0, 10])

        # auto start a forward flight
        self.start_forward_flight()


    def custom_calculate_position(self, tz):
        return self.props['start_position']


# class VectorFlightPlan(FlightPlan):
#     def __init__(self, decision_handler=None, duration=None, vector=(0,0), start_position=(0,0)):
#         # call super
#         super().__init__(decision_handler=decision_handler, duration=duration)
#
#         # save props
#         self.start_position = list(start_position)
#         self.vector = list(vector)
#
#     def custom_calculate_position(self, tz):
#         positions = []
#         for i in range(0, len(self.vector)):
#             positions.append(self.start_position[i] + self.vector[i] * tz)
#
#         return positions

# --------------------------------------------------
#    Plugin
# --------------------------------------------------
class pluginDrawing:
    """ plugin for Canvas Drawing application """
    # --------------------------------------------------
    #    Constructor and Plugin Registration
    # --------------------------------------------------
    def __init__(self, canvas_context_working_name, canvas_context_target_name):
        """ init """
        # attach drawing function to every jsc instance
        self._drawing = JSDraw(canvas_context_working_name, canvas_context_target_name)
        self.jsc_exposed_funcs = {'drawing': lambda jsc : self._drawing}

        # cache the javascript for injection
        f = open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'pylinkjsDraw.js'), 'rb')
        self._plugin_javascript = f.read()
        f.close()

    def inject_javascript(self):
        # return the javascript to inject into every page
        return self._plugin_javascript
    
    def register(self, kwargs):
        """ callback to register this plugin with the framework """
        # nothing to register for this plugin
        pass
