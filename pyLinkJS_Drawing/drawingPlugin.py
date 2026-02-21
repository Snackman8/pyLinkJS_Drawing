"""Canvas drawing and animation primitives for pyLinkJS.

Provides command-queued canvas rendering (via browser JavaScript), render
object types (shapes, images, text), motion plans, and plugin hooks used by
pyLinkJS_Drawing applications.
"""

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
    """Queue-based helper for issuing canvas drawing commands through pyLinkJS."""
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
        'textBaseline': None,}

    # standard canvas drawing properties which are not strings
    DRAWING_PROPS = {
        'lineWidth': None,
        'fillStyleObj': None,
        }

    # union of all the canvas drawing properties
    ALL_DRAWING_PROPS = DRAWING_PROPS | DRAWING_PROPS_STR

    def __init__(self, canvas_context_working_name, canvas_context_target_name):
        """Initialize a JavaScript drawing command queue.

        Args:
            canvas_context_working_name: Name of the off-screen canvas context.
            canvas_context_target_name: Name of the on-screen canvas context that
                receives the final flipped image.
        """
        self.__dict__['_canvas_context_working_name'] = canvas_context_working_name
        self.__dict__['_canvas_context_target_name'] = canvas_context_target_name
        self.__dict__['_commands'] = []

    def __getattr__(self, key):
        """Resolve dynamic drawing attributes and drawing function proxies.

        Args:
            key: Canvas property name or drawing function name.

        Returns:
            Current tracked drawing property value, or a proxy callable for
            drawing functions defined in ``DRAWING_FUNCS``.

        Raises:
            AttributeError: If ``key`` is not a supported property or function.
        """
        if key in self.ALL_DRAWING_PROPS:
            return self.DRAWING_PROPS[key]
        if key in self.DRAWING_FUNCS:
            return partial(self._proxy_func_handler, key, self.DRAWING_FUNCS[key])

        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{key}")

    def __setattr__(self, key, value):
        """Queue updates to canvas drawing properties.

        This overload tracks property state and appends JavaScript assignment
        commands into the render queue.

        Args:
            key: Canvas property name.
            value: Property value to assign.
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
                # add the command to the command queue which will be sent to javascript
                self._commands.append(['{context_name}.{prop_name} = {value};', kwargs])
            else:
                if key in self.DRAWING_PROPS:
                    # add the command to the command queue which will be sent to javascript
                    self._commands.append(['{context_name}.{prop_name} = {value};', kwargs])
                else:
                    # add the command to the command queue which will be sent to javascript
                    self._commands.append(['{context_name}.{prop_name} = \'{value}\';', kwargs])
        else:
            return super().__setattr__(key, value)

    def _proxy_func_handler(self, func_name, arg_names, *args, **kwargs):
        """Queue a drawing call with optional per-call property overrides.

        Positional arguments are mapped onto ``arg_names`` and combined with
        keyword arguments to build the final JavaScript draw command.

        Args:
            func_name: Name of the JavaScript draw function suffix.
            arg_names: Ordered argument names expected by the function.
            *args: Positional argument values for ``arg_names``.
            **kwargs:
                - Drawing call parameters named in ``arg_names``.
                - Optional drawing property overrides supported by
                  ``JSDraw.DRAWING_PROPS``.

                Note:
                - Keys listed in ``JSDraw.DRAWING_PROPS`` are treated as
                  per-call property overrides and are not passed through as draw
                  function arguments.
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
        """Queue a clear operation for the working canvas."""
        self._commands.append(['clear({context_name});', {'context_name': self._canvas_context_working_name}])

    def clear_renderer(self):
        """Clear all queued drawing commands for this renderer instance."""
        self._commands = []

    def context_restore(self):
        """Queue ``restore()`` on the working canvas context."""
        self._commands.append(['{context_name}.restore();', {'context_name': self._canvas_context_working_name}])

    def context_save(self):
        """Queue ``save()`` on the working canvas context."""
        self._commands.append(['{context_name}.save();', {'context_name': self._canvas_context_working_name}])

    def create_image(self, name, image_src):
        """Queue creation of a JavaScript ``Image`` object.

        Args:
            name: JavaScript variable name to assign the image object to.
            image_src: Image URL or path assigned to ``image.src``.

        Returns:
            None.
        """
        kwargs = {'name': name, 'image_src': image_src}
        self._commands.append(['{name} = new Image(100, 100);', kwargs])
        self._commands.append(["{name}.src = '{image_src}';", kwargs])

    def gradient_radial(self, name, x0, y0, r0, x1, y1, r1, color_stops):
        """Queue creation of a radial gradient in the working context.

        Args:
            name: JavaScript variable name for the gradient object.
            x0: X coordinate of the start circle center.
            y0: Y coordinate of the start circle center.
            r0: Radius of the start circle.
            x1: X coordinate of the end circle center.
            y1: Y coordinate of the end circle center.
            r1: Radius of the end circle.
            color_stops: Iterable of ``(offset, color)`` pairs passed to
                ``addColorStop``.

        Returns:
            None.
        """
        kwargs = {'context_name': self._canvas_context_working_name, 'name': name, 'x0': x0, 'y0': y0, 'r0': r0, 'x1': x1, 'y1': y1, 'r1': r1}
        self._commands.append(['{name} = {context_name}.createRadialGradient({x0}, {y0}, {r0}, {x1}, {y1}, {r1});', kwargs])
        for cs in color_stops:
            self._commands.append(['{name}.addColorStop({r}, \'{c}\');', {'name': name, 'r': cs[0], 'c': cs[1]}])

    def render(self, jsc, clear=True):
        """Render queued commands and flip working canvas to display canvas.

        Builds JavaScript from the queued commands, executes it on the client,
        and performs a final double-buffer flip from working to target context.

        Args:
            jsc: pyLinkJS JavaScript client used to evaluate render code.
            clear: If ``True``, clear the command queue after a successful
                render.

        Returns:
            None.
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
    """Base class for time-based motion planning of render objects.

    Flight plans can be started immediately or in the future, optionally capped
    by duration, and paused/resumed while preserving elapsed progress.
    """
    def __init__(self, decision_handler=[], duration=None, name=None):
        """Initialize base flight plan state.

        Args:
            decision_handler: Optional sequence of callbacks invoked before each
                position calculation.
            duration: Optional max flight duration in seconds.
            name: Optional flight plan identifier.
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
        """Calculate elapsed flight time used for motion equations.

        Args:
            t: Absolute current time (seconds since epoch).

        Returns:
            Elapsed active time for this flight plan, clamped by duration when
            configured.
        """
        try:
            # if the flight plan is paused, return the time offset when it was paused
            if self.props['pause_time'] is not None:
                return self.props['pause_time'] - self.props['start_time']

            # if the flight plan has no start time or the time is before the start time, return 0
            if self.props['start_time'] is None or t <= self.props['start_time']:
                return 0

            # if the flight plan has no duration, return the elapsed flight time
            tdelta = t - self.props['start_time']
            if self.props['duration'] is None:
                return tdelta

            # return either the elapsed flight time or the duration, whichever is less
            return min(tdelta, self.props['duration'])
        except:
            raise Exception()

    def _set_default_prop_list(self, key, val):
        """Ensure a forward-flight property exists as a mutable list.

        Args:
            key: Property name in ``self.fprops``.
            val: Default iterable value to copy when ``key`` is missing.
        """
        self.fprops[key] = list(self.fprops.get(key, val))

    def calculate_position(self, renderObj, t):
        """Compute world-space position for a render object at time ``t``.

        Args:
            renderObj: Render object whose position is being calculated.
            t: Absolute current time.

        Returns:
            Position list in world coordinates, including parent offsets when
            applicable.
        """
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
        """Compute position values for subclass-specific motion models.

        Args:
            tz: Elapsed active flight time in seconds.
        """
        raise NotImplementedError

    def get_positions(self, renderObj, t):
        """Run decision handlers, then return current object positions.

        Args:
            renderObj: Render object whose position is being computed.
            t: Absolute current time.
        """
        # check the decision handler
        if self.decision_handler:
            for dh_func in self.decision_handler:
                if callable(dh_func):
                    dh_func(renderObj, self, t)
                elif hasattr(dh_func, 'decide'):
                    dh_func.decide(renderObj, self, t)

        return self.calculate_position(renderObj, t)

    def is_active(self, t):
        """Return ``True`` when this flight plan is currently active."""
        if self.props['start_time'] is None or t <= self.props['start_time']:
            return False

        if self.props['end_time'] is None and t <= self.props['end_time']:
            return True

        return False

    def pause(self):
        """Pause the flight plan at the current wall-clock time."""
        self.props['pause_time'] = time.time()

    def resume(self):
        """Resume a paused flight plan and preserve elapsed progress."""
        delta_time = time.time() - self.props['pause_time']
        self.props['start_time'] += delta_time
        self.props['end_time'] += delta_time
        self.props['pause_time'] = None

    def start_forward_flight(self, start_time=-99999999):
        """Initialize properties for forward playback.

        Args:
            start_time: Absolute start time. Uses ``time.time()`` when left as
                default sentinel.
        """
        self.props = deepcopy(self.fprops)
        if start_time == -99999999:
            start_time = time.time()
        self.props['start_time'] = start_time

    def start_reverse_flight(self, start_time=-99999999):
        """Initialize properties for reverse playback.

        Args:
            start_time: Absolute reverse start time.
        """
        raise NotImplementedError


class RenderObject():
    """Base render tree node for drawable objects and containers."""
    def __init__(self, flightplan=None, **kwargs):
        """Initialize a render object with defaults, props, and hierarchy state.

        Args:
            flightplan: Optional ``FlightPlan`` controlling object position.
            **kwargs:
                - ``name`` (str): Object name. Default is a UUID string.
                - ``fillStyle`` (str | None): Fill color/style. ``None`` is
                  normalized to ``'rgba(0, 0, 0, 0)'``.
                - ``strokeStyle`` (str): Stroke color/style. Default
                  ``'black'``.
                - ``glow`` (bool): Enable glow rendering. Default ``False``.
                - ``glow_attenuation`` (list[float]): RGBA attenuation factors
                  for glow color. Default ``[0.33, 0.33, 0.33, 0.03]``.
                - ``glow_width`` (int): Glow line count. Default ``40``.
                - ``clickable`` (bool): Hit-test intent flag. Default
                  ``False``.
                - ``scale`` (float): Object scale factor. Default ``1``.
                - ``visible`` (bool): Render visibility flag. Default ``True``.

                Note:
                - Any additional keys are preserved in ``self.props``.
                - If both ``foo`` and ``fooObj`` are provided, ``foo`` is
                  removed during cleanup so the object reference variant is used.
        """
        # defaults
        kwargs['name'] = kwargs.get('name', f'{uuid.uuid4()}')
        kwargs['fillStyle'] = kwargs.get('fillStyle', 'white')
        kwargs['glow'] = kwargs.get('glow', False)
        kwargs['glow_attenuation'] = kwargs.get('glow_attenuation', [0.33, 0.33, 0.33, 0.03])
        kwargs['glow_width'] = kwargs.get('glow_width', 40)
        kwargs['clickable'] = kwargs.get('clickable', False)
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

    def _point_in_obj(self, x, y, t):
        """Return whether a world-space point intersects this object.

        Subclasses override this method to implement object-specific hit tests.

        Args:
            x: World-space x coordinate.
            y: World-space y coordinate.
            t: Absolute current time.
        """
        return None

    def add_child(self, childobj):
        """Attach a child render object to this node.

        Args:
            childobj: Child ``RenderObject`` instance to attach.
        """
        self.children[childobj.props['name']] = childobj
        childobj.parent = self

    @classmethod
    def color_calculate_glow(cls, rgba_string, glow_attenuation):
        """Return a dimmed RGBA color used to render glow outlines.

        Args:
            rgba_string: Input color in ``rgba(r,g,b,a)`` format.
            glow_attenuation: RGBA attenuation multipliers.
        """
        color_glow = cls.color_decode(rgba_string)
        for i in range(0, 4):
            color_glow[i] = color_glow[i] * glow_attenuation[i]
        color_glow = cls.color_encode(color_glow)
        return color_glow

    @classmethod
    def color_decode(cls, rgba_string):
        """Parse an ``rgba(r,g,b,a)`` string into numeric channel values.

        Args:
            rgba_string: Color string to decode.
        """
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
        """Convert numeric RGBA values into an ``rgba(...)`` string.

        Args:
            rgba_list: Sequence ``[r, g, b, a]``.
        """
        return f'rgba({rgba_list[0]}, {rgba_list[1]}, {rgba_list[2]}, {rgba_list[3]})'

    def customrender(self, f, t):
        """Render this object when subclasses do not provide custom logic.

        Args:
            f: ``JSDraw`` command queue.
            t: Absolute current time.
        """
        try:
            positions = self.flightplan.get_positions(self, t)
        except:
            positions = [0, 0]
        f.circle(x=positions[0], y=positions[1], r=20 * self.props['scale'], fillStyle='white', strokeStyle='red')

    def draw_glow(self, partial_func, **kwargs):
        """Render optional glow strokes, then render the normal stroke.

        Args:
            partial_func: Callable used to draw a single stroke instance.
            **kwargs:
                - ``strokeStyle`` (str): Base stroke color.
                - ``glow_attenuation`` (list[float]): Per-channel glow
                  attenuation overrides.
                - ``glow_width`` (int): Glow width override.
        """
        # render the glow if needed
        if self.props.get('glow', False):
            # calculate glow color
            color_glow = self.color_calculate_glow(
                kwargs.get('strokeStyle', self.props.get('strokeStyle', 'rgba(0,0,0,0)')),
                kwargs.get('glow_attenuation', self.props['glow_attenuation']))

            # draw the glow lines
            for i in range(1, kwargs.get('glow_width', self.props.get('glow_width'))):
                partial_func(lineWidth=i, strokeStyle=color_glow)

        # draw the hard border
        partial_func()

    def point_in_obj(self, x, y, t):
        """Return a flat list of objects hit by point ``(x, y)`` at time ``t``."""
        # init
        retval = []

        # check if this point is in this object
        if self._point_in_obj(x, y, t):
            retval.append(self)

        # search the children
        for c in list(self.children.values()):
            retval = retval + c.point_in_obj(x, y, t)

        return retval

    def prerender(self, f, t):
        """Save context and apply this object's drawing properties.

        Args:
            f: ``JSDraw`` command queue.
            t: Absolute current time.
        """
        # apply the properties globally
        f.context_save()
        for k in self.props:
            if k in JSDraw.ALL_DRAWING_PROPS:
                setattr(f, k, self.props[k])

    def postrender(self, f, t):
        """Restore context after this object and its children are rendered."""
        f.context_restore()

    def render(self, f, t):
        """Render this object subtree using object properties as defaults."""
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
        """Set object scale recursively for this node and all descendants.

        Args:
            new_scale: New scalar multiplier.
        """
        self.props['scale'] = new_scale
        for c in self.children.values():
            c.set_scale(new_scale)


# --------------------------------------------------
#    Implementation Classes
# --------------------------------------------------
class BounceHandler():
    """Decision handler that bounces moving objects within rectangular bounds."""
    def __init__(self, x1, y1, r1, x2, y2, r2):
        """Initialize bounce limits.

        Args:
            x1: Left boundary.
            y1: Top boundary.
            r1: Minimum radius boundary.
            x2: Right boundary.
            y2: Bottom boundary.
            r2: Maximum radius boundary.
        """
        self.x1 = x1
        self.y1 = y1
        self.r1 = r1
        self.x2 = x2
        self.y2 = y2
        self.r2 = r2

    def decide(self, renderObj, fp, t):
        """Update vector direction when motion exceeds configured boundaries.

        Args:
            renderObj: Render object being evaluated.
            fp: Active flight plan with vector components.
            t: Absolute current time.
        """
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
    """Renderable ellipse."""
    def __init__(self, flightplan=None, **kwargs):
        """Initialize ellipse geometry and default flight plan behavior.

        Args:
            flightplan: Optional ``FlightPlan`` for motion.
            **kwargs:
                - ``x`` (float): Initial x position.
                - ``y`` (float): Initial y position.
                - ``radiusX`` (float): Horizontal radius. Default ``100``.
                - ``radiusY`` (float): Vertical radius. Default ``50``.
                - ``rotation`` (float): Ellipse rotation in radians. Default
                  ``0``.
                - ``start_angle`` (float): Start angle in radians. Default
                  ``0``.
                - ``end_angle`` (float): End angle in radians. Default
                  ``math.pi * 2``.
                - ``counterclockwise`` (int | bool): Arc direction flag.
                  Default ``0``.
                - Any additional ``RenderObject`` properties.

                Note:
                - If ``flightplan`` is ``None``, ``x`` and ``y`` are required
                  and are used to create a ``StaticFlightPlan``.
        """
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
        """Render this ellipse using current flight-plan position."""
        if self.flightplan:
            # calculate new position
            positions = self.flightplan.get_positions(self, t)
            f.ellipse(positions[0], positions[1], self.props['radiusX'] * self.props['scale'], self.props['radiusY'] * self.props['scale'],
                      self.props['rotation'], self.props['startAngle'], self.props['endAngle'], self.props['counterclockwise'])

    def _point_in_obj(self, x, y, t):
        """Return this object when point ``(x, y)`` is inside the ellipse."""
        if self.flightplan:
            positions = self.flightplan.get_positions(self, t)
            dx = (x - positions[0]) / (self.props['radiusX'] * self.props['scale'])
            dy = (y - positions[1]) / (self.props['radiusY'] * self.props['scale'])
            if (dx * dx + dy * dy - 1) <= 0:
                return self


class CircleObject(EllipseObject):
    """Renderable circle convenience wrapper around ``EllipseObject``."""
    def __init__(self, flightplan=None, **kwargs):
        """Initialize a circle with ``radius`` mapped to ellipse radii.

        Args:
            flightplan: Optional ``FlightPlan`` for motion.
            **kwargs:
                - ``radius`` (float): Circle radius. Default ``100``.
                - Any supported ``EllipseObject``/``RenderObject`` properties.
        """
        kwargs['radius'] = kwargs.get('radius', 100)
        super().__init__(flightplan=flightplan, **kwargs)

    def customrender(self, f, t):
        """Render circle by syncing ``radiusX``/``radiusY`` to ``radius``.

        Args:
            f: ``JSDraw`` command queue.
            t: Absolute current time.
        """
        self.props['radiusX'] = self.props['radius']
        self.props['radiusY'] = self.props['radius']
        super().customrender(f, t)


class RoundRectObject(RenderObject):
    """Renderable rounded rectangle."""
    def __init__(self, flightplan=None, **kwargs):
        """Initialize rounded rectangle dimensions and corner radii.

        Args:
            flightplan: Optional ``FlightPlan`` for motion.
            **kwargs:
                - ``x`` (float): Initial x position.
                - ``y`` (float): Initial y position.
                - ``width`` (float): Rectangle width. Default ``200``.
                - ``height`` (float): Rectangle height. Default ``10``.
                - ``radii`` (list[float]): Corner radii. Default
                  ``[20, 20, 40, 40]``.
                - Any additional ``RenderObject`` properties.

                Note:
                - If ``flightplan`` is ``None``, ``x`` and ``y`` are required
                  and are used to create a ``StaticFlightPlan``.
        """
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
        """Render the rounded rectangle at the current position.

        Args:
            f: ``JSDraw`` command queue.
            t: Absolute current time.
        """
        if self.flightplan:
            # calculate new position
            positions = self.flightplan.get_positions(self, t)
            f.roundRect(positions[0], positions[1], self.props['width'] * self.props['scale'], self.props['height'] * self.props['scale'], self.props['radii'])

    def _point_in_obj(self, x, y, t):
        """Return this object when point ``(x, y)`` is inside its bounds."""
        if self.flightplan:
            positions = self.flightplan.get_positions(self, t)
            x = x - positions[0]
            y = y - positions[1]
            if (x >= 0) and (x < self.props['width'] * self.props['scale']) and (y >= 0) and (y < self.props['height'] * self.props['scale']):
                return self


class ImageObject(RoundRectObject):
    """Renderable image object with optional CSS filter string."""
    def __init__(self, flightplan=None, **kwargs):
        """Initialize image reference, dimensions, and optional filter.

        Args:
            flightplan: Optional ``FlightPlan`` for motion.
            **kwargs:
                - ``image_name`` (str | None): JavaScript image variable name.
                  Default ``None``.
                - ``width`` (float | None): Draw width. Default ``None``.
                - ``height`` (float | None): Draw height. Default ``None``.
                - ``filter_str`` (str): CSS filter string. Default ``''``.
                - Any supported ``RoundRectObject``/``RenderObject``
                  properties.
        """
        kwargs['image_name'] = kwargs.get('image_name', None)
        kwargs['width'] = kwargs.get('width', None)
        kwargs['height'] = kwargs.get('height', None)
        kwargs['filter_str'] = kwargs.get('filter_str', '')
        super().__init__(flightplan=flightplan, **kwargs)

    def customrender(self, f, t):
        """Render the image when ``image_name`` is set.

        Args:
            f: ``JSDraw`` command queue.
            t: Absolute current time.
        """
        if self.flightplan:
            # calculate new position
            positions = self.flightplan.get_positions(self, t)
            if self.props['image_name'] is not None:
                f.image(self.props['image_name'], positions[0], positions[1], self.props['width'], self.props['height'], filter_str=self.props['filter_str'])

    def _point_in_obj(self, x, y, t):
        """Return this object when point ``(x, y)`` is inside image bounds."""
        if self.flightplan:
            positions = self.flightplan.get_positions(self, t)
            x = x - positions[0]
            y = y - positions[1]
            if (x >= 0) and (x < self.props['width'] * self.props['scale']) and (y >= 0) and (y < self.props['height'] * self.props['scale']):
                return self


class RectObject(RoundRectObject):
    """Renderable rectangle (``RoundRectObject`` with zero corner radii)."""
    def __init__(self, flightplan=None, **kwargs):
        """Initialize rectangle with square corners.

        Args:
            flightplan: Optional ``FlightPlan`` for motion.
            **kwargs:
                - Any supported ``RoundRectObject``/``RenderObject``
                  properties.

                Note:
                - ``radii`` is forced to ``[0, 0, 0, 0]``.
        """
        kwargs['radii'] = [0, 0, 0, 0]
        super().__init__(flightplan=flightplan, **kwargs)


class TextObject(RenderObject):
    """Renderable text object."""
    def __init__(self, flightplan=None, **kwargs):
        """Initialize text content and default static flight plan behavior.

        Args:
            flightplan: Optional ``FlightPlan`` for motion.
            **kwargs:
                - ``x`` (float): Initial x position.
                - ``y`` (float): Initial y position.
                - ``text_str`` (str): Text to render. Default ``'ABCD'``.
                - ``fillStyle`` (str): Text fill style.
                - ``strokeStyle`` (str): Stroke style.
                - Any additional ``RenderObject`` properties.

                Note:
                - If ``flightplan`` is ``None``, ``x`` and ``y`` are required
                  and are used to create a ``StaticFlightPlan``.
        """
        kwargs['text_str'] = kwargs.get('text_str', 'ABCD')
        if flightplan is None:
            if 'x' in kwargs and 'y' in kwargs:
                flightplan = StaticFlightPlan(start_position=(kwargs['x'], kwargs['y']))
            else:
                raise Exception('Either flightplan or x,y must be passed in')
        super().__init__(flightplan=flightplan, **kwargs)

    def customrender(self, f, t):
        """Render text at the current flight-plan position."""
        if self.flightplan:
            # calculate new position
            positions = self.flightplan.get_positions(self, t)
            f.text(text_str=self.props['text_str'], x=positions[0], y=positions[1], fillStyle=self.props['fillStyle'])

    def point_in_obj(self, x, y, t):
        """Disable hit-testing for text objects.

        Args:
            x: World-space x coordinate.
            y: World-space y coordinate.
            t: Absolute current time.
        """
        return []


# --------------------------------------------------
#    Flight Plans
# --------------------------------------------------
class OrbitFlightPlan(FlightPlan):
    """Flight plan for orbital motion around a configurable center."""
    def __init__(self, decision_handler=[], duration=None, name=None, **kwargs):
        """Initialize orbit motion around a center point.

        Args:
            decision_handler: Optional callbacks run before position updates.
            duration: Optional max flight duration in seconds.
            name: Optional flight plan identifier.
            **kwargs:
                - ``center`` (list[float]): Orbit center ``[x, y]``. Default
                  ``[0, 0]``.
                - ``vector_start`` (list[float]): Initial orbit state.
                  Default ``[0, 0]``.
                - ``vector`` (list[float]): Per-second change values. Default
                  ``[0, 0]``.

                Note:
                - Extra keys are stored in ``self.fprops``.
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
        """Calculate orbital position values for elapsed time ``tz``."""
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
        """Initialize reverse playback from the current orbit state.

        Args:
            start_time: Absolute reverse start time. Uses ``time.time()`` when
                left as default sentinel.
        """
        tz = self._calculate_time_from_zero(time.time())
        self.props = deepcopy(self.fprops)

        for i in range (0, len(self.props['vector_start'])):
            self.props['vector_start'][i] = self.props['vector_start'][i] + self.props['vector'][i] * tz

        self.props['vector'] = [-x for x in self.props['vector']]

        if start_time == -99999999:
            start_time = time.time()

        self.props['start_time'] = start_time


class StaticFlightPlan(FlightPlan):
    """Flight plan that keeps an object fixed at a constant position."""
    def __init__(self, decision_handler=None, **kwargs):
        """Initialize a static position flight plan.

        Args:
            decision_handler: Optional decision callbacks.
            **kwargs:
                - ``start_position`` (list[float]): Constant returned position.
                  Default ``[0, 0, 10]``.

                Note:
                - Extra keys are stored in ``self.fprops``.
        """
        # call super
        super().__init__(decision_handler=decision_handler)

        # additional fprops
        self.fprops.update(kwargs.copy())
        self._set_default_prop_list('start_position', [0, 0, 10])

        # auto start a forward flight
        self.start_forward_flight()


    def custom_calculate_position(self, tz):
        """Return the fixed start position regardless of elapsed time.

        Args:
            tz: Elapsed active flight time in seconds.
        """
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
    """pyLinkJS plugin that injects canvas drawing helpers."""
    # --------------------------------------------------
    #    Constructor and Plugin Registration
    # --------------------------------------------------
    def __init__(self, canvas_context_working_name, canvas_context_target_name):
        """Initialize the drawing plugin.

        Args:
            canvas_context_working_name: Off-screen canvas context name.
            canvas_context_target_name: On-screen canvas context name.
        """
        # attach drawing function to every jsc instance
        self._drawing = JSDraw(canvas_context_working_name, canvas_context_target_name)
        self.jsc_exposed_funcs = {'drawing': lambda jsc : self._drawing}

        # cache the javascript for injection
        f = open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'pylinkjsDraw.js'), 'r')
        self._plugin_javascript = f.read()
        f.close()

    def inject_html_top(self):
        """Return script tag HTML used to inject drawing JavaScript helpers."""
        # return the javascript to inject into every page
        return '<script>' + self._plugin_javascript + '</script>'

    def register(self, kwargs):
        """Plugin registration hook required by pyLinkJS.

        Args:
            kwargs: Framework registration context.
        """
        # nothing to register for this plugin
        pass
