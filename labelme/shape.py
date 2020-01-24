import copy
import math

from qtpy import QtCore
from qtpy import QtGui

import labelme.utils

class NoPointError(Exception):
    pass

# TODO(unknown):
# - [opt] Store paths instead of creating new ones at each paint.


DEFAULT_LINE_COLOR = QtGui.QColor(0, 255, 0, 128)
DEFAULT_FILL_COLOR = QtGui.QColor(255, 0, 0, 128)
DEFAULT_SELECT_LINE_COLOR = QtGui.QColor(255, 255, 255)
DEFAULT_SELECT_FILL_COLOR = QtGui.QColor(0, 128, 255, 155)
DEFAULT_VERTEX_FILL_COLOR = QtGui.QColor(0, 255, 0, 255)
DEFAULT_HVERTEX_FILL_COLOR = QtGui.QColor(255, 0, 0)

QUADRATIC_BEZIER_ORDER = 2
CUBIC_BEZIER_ORDER = 3

class Shape(object):

    P_SQUARE, P_ROUND = 0, 1

    MOVE_VERTEX, NEAR_VERTEX = 0, 1

    # The following class variables influence the drawing of all shape objects.
    line_color = DEFAULT_LINE_COLOR
    fill_color = DEFAULT_FILL_COLOR
    select_line_color = DEFAULT_SELECT_LINE_COLOR
    select_fill_color = DEFAULT_SELECT_FILL_COLOR
    vertex_fill_color = DEFAULT_VERTEX_FILL_COLOR
    hvertex_fill_color = DEFAULT_HVERTEX_FILL_COLOR
    point_type = P_ROUND
    point_size = 8
    scale = 1.0

    def __init__(self, label=None, line_color=None, shape_type=None,
                 flags=None):
        self.label = label
        self.points = []
        self.segments = []
        self.points_in_segments = 0
        self.fill = False
        self.selected = False
        self.shape_type = shape_type
        self.flags = flags

        self._highlightIndex = None
        self._highlightMode = self.NEAR_VERTEX
        self._highlightSettings = {
            self.NEAR_VERTEX: (4, self.P_ROUND),
            self.MOVE_VERTEX: (1.5, self.P_SQUARE),
        }

        self._closed = False

        if line_color is not None:
            # Override the class line_color attribute
            # with an object attribute. Currently this
            # is used for drawing the pending line a different color.
            self.line_color = line_color

        self.shape_type = shape_type

    @property
    def shape_type(self):
        return self._shape_type

    @shape_type.setter
    def shape_type(self, value):
        if value is None:
            value = 'polygon'
        if value not in ['polygon', 'rectangle', 'point',
           'line', 'circle', 'linestrip', 'curve']:
            raise ValueError('Unexpected shape_type: {}'.format(value))
        self._shape_type = value

    def close(self):
        self._closed = True

    def addSegment(self, seg_begin, seg_len):
        if len(self.segments) == 0:
            self.points_in_segments = 0
            self.points_in_segments += seg_len
        else:
            self.points_in_segments += (seg_len - 1)
        new_segment = [seg_begin, seg_len]
        self.segments.append(new_segment)

    def addPointToSegment(self, point, seg_id):
        self.segments[seg_id][1] += 1

    def createSegment(self, point, degree_increment, new_p=0):
        if point == self.points[-1]:
            size = QUADRATIC_BEZIER_ORDER + degree_increment
            seg_begin = len(self.points) - size
            seg_len = size
        else:
            size = CUBIC_BEZIER_ORDER + degree_increment
            self.insertPoint(max(len(self.points) - 1, 1), new_p)
            seg_begin = len(self.points) - size
            seg_len = size
            self.points.append(point)
        self.addSegment(seg_begin, seg_len)

    def addPoint(self, point, is_release=False, new_p=0):
        if is_release and self.shape_type == 'curve':
            if point == self.points[-1] and len(self.points) == 1:
                self.points_in_segments += 1
            elif len(self.segments) == 0 and len(self.points) == 1:
                self.points.append(point)
                self.points_in_segments += 1
            else:
                try:
                    degree_increment = max(len(self.points) - self.points_in_segments - 1, 0)
                    self.createSegment(point, degree_increment, new_p)
                    if point == self.points[0]:
                        self.points.pop(-1)
                        self.close()
                except NoPointError as e:
                    assert False, "new_p is empty !!!"
        else:
            if self.points and point == self.points[0]:
                degree_increment = max(len(self.points) - self.points_in_segments, 0)
                if self.shape_type == 'curve' and degree_increment == 1:
                    size = QUADRATIC_BEZIER_ORDER + degree_increment
                    seg_begin = len(self.points) - size + 1
                    seg_len = size
                    self.addSegment(seg_begin, seg_len)
                self.close()
            else:
                self.points.append(point)

    def canAddPoint(self):
        return self.shape_type in ['polygon', 'linestrip']

    def popPoint(self):
        if self.points:
            return self.points.pop()
        return None

    def insertPoint(self, i, point):
        self.points.insert(i, point)

    def removePoint(self, i):
        self.points.pop(i)

    def isClosed(self):
        return self._closed

    def setOpen(self):
        self._closed = False

    def getRectFromLine(self, pt1, pt2):
        x1, y1 = pt1.x(), pt1.y()
        x2, y2 = pt2.x(), pt2.y()
        return QtCore.QRectF(x1, y1, x2 - x1, y2 - y1)

    def paint(self, painter, is_line=False):
        if self.points:
            color = self.select_line_color \
                if self.selected else self.line_color
            pen = QtGui.QPen(color)
            dash_pen = QtGui.QPen(QtCore.Qt.red, 0.5, QtCore.Qt.DashLine)
            dash_pen.setWidth(0)
            # Try using integer sizes for smoother drawing(?)
            pen.setWidth(max(1, int(round(2.0 / self.scale))))
            painter.setPen(pen)

            line_path = QtGui.QPainterPath()
            vrtx_path = QtGui.QPainterPath()
            source_curve_path = QtGui.QPainterPath()

            pts = []

            if self.shape_type == 'rectangle':
                assert len(self.points) in [1, 2]
                if len(self.points) == 2:
                    rectangle = self.getRectFromLine(*self.points)
                    line_path.addRect(rectangle)
                for i in range(len(self.points)):
                    self.drawVertex(vrtx_path, i)
            elif self.shape_type == "circle":
                assert len(self.points) in [1, 2]
                if len(self.points) == 2:
                    rectangle = self.getCircleRectFromLine(self.points)
                    line_path.addEllipse(rectangle)
                for i in range(len(self.points)):
                    self.drawVertex(vrtx_path, i)
            elif self.shape_type == "linestrip":
                line_path.moveTo(self.points[0])
                for i, p in enumerate(self.points):
                    line_path.lineTo(p)
                    self.drawVertex(vrtx_path, i)
            elif self.shape_type == "curve":
                line_path.moveTo(self.points[0])
                source_curve_path.moveTo(self.points[0])
                for i, p in enumerate(self.points):
                    self.drawVertex(vrtx_path, i)
                    source_curve_path.lineTo(p)
                for s in self.segments:
                    line_path.moveTo(self.points[s[0]])
                    self.drawSegment(line_path, s)
                    pts.append(self.points[s[0]])
                if self.isClosed():
                    line_path.lineTo(self.points[0])
            else:
                line_path.moveTo(self.points[0])
                # Uncommenting the following line will draw 2 paths
                # for the 1st vertex, and make it non-filled, which
                # may be desirable.
                # self.drawVertex(vrtx_path, 0)

                for i, p in enumerate(self.points):
                    line_path.lineTo(p)
                    self.drawVertex(vrtx_path, i)
                if self.isClosed():
                    line_path.lineTo(self.points[0])

            if self.shape_type == "curve":

                if self.isClosed():
                    qpts = QtGui.QPolygonF(pts)
                    line_path.addPolygon(qpts)
                    line_path = line_path.simplified()
                if self.isClosed() or is_line:
                    painter.setPen(dash_pen)
                    painter.drawPath(source_curve_path)
                    painter.setPen(pen)
            painter.drawPath(line_path)
            painter.drawPath(vrtx_path)

            if self.fill:
                color = self.select_fill_color \
                    if self.selected else self.fill_color
                painter.fillPath(line_path, color)

    def drawSegment(self, path, segment):
        beg_p_ind = segment[0]
        if segment[1] == 4:  # cubic bezier
            path.cubicTo(self.points[beg_p_ind + 1], self.points[beg_p_ind + 2], self.points[beg_p_ind + 3])
        elif segment[1] == 3:  # square bezier
            if len(self.points) >= segment[0] + segment[1]:
                path.quadTo(self.points[beg_p_ind + 1], self.points[beg_p_ind + 2])
            else:
                path.quadTo(self.points[beg_p_ind + 1], self.points[0])
        else:  # line
            path.lineTo(self.points[beg_p_ind + 1])

    def drawVertex(self, path, i):
        d = self.point_size / self.scale
        shape = self.point_type
        point = self.points[i]
        if i == self._highlightIndex:
            size, shape = self._highlightSettings[self._highlightMode]
            d *= size
        if self._highlightIndex is not None:
            self.vertex_fill_color = self.hvertex_fill_color
        else:
            self.vertex_fill_color = Shape.vertex_fill_color
        if shape == self.P_SQUARE:
            path.addRect(point.x() - d / 2, point.y() - d / 2, d, d)
        elif shape == self.P_ROUND:
            path.addEllipse(point, d / 2.0, d / 2.0)
        else:
            assert False, "unsupported vertex shape"

    def nearestVertex(self, point, epsilon):
        min_distance = float('inf')
        min_i = None
        for i, p in enumerate(self.points):
            dist = labelme.utils.distance(p - point)
            if dist <= epsilon and dist < min_distance:
                min_distance = dist
                min_i = i
        return min_i

    def nearestEdge(self, point, epsilon):
        min_distance = float('inf')
        post_i = None
        for i in range(len(self.points)):
            line = [self.points[i - 1], self.points[i]]
            dist = labelme.utils.distancetoline(point, line)
            if dist <= epsilon and dist < min_distance:
                min_distance = dist
                post_i = i
        return post_i

    def containsPoint(self, point):
        return self.makePath().contains(point)

    def getCircleRectFromLine(self, line):
        """Computes parameters to draw with `QPainterPath::addEllipse`"""
        if len(line) != 2:
            return None
        (c, point) = line
        r = line[0] - line[1]
        d = math.sqrt(math.pow(r.x(), 2) + math.pow(r.y(), 2))
        rectangle = QtCore.QRectF(c.x() - d, c.y() - d, 2 * d, 2 * d)
        return rectangle

    def makePath(self):
        if self.shape_type == 'rectangle':
            path = QtGui.QPainterPath()
            if len(self.points) == 2:
                rectangle = self.getRectFromLine(*self.points)
                path.addRect(rectangle)
        elif self.shape_type == "circle":
            path = QtGui.QPainterPath()
            if len(self.points) == 2:
                rectangle = self.getCircleRectFromLine(self.points)
                path.addEllipse(rectangle)
        else:
            path = QtGui.QPainterPath(self.points[0])
            for p in self.points[1:]:
                path.lineTo(p)
        return path

    def boundingRect(self):
        return self.makePath().boundingRect()

    def moveBy(self, offset):
        self.points = [p + offset for p in self.points]

    def moveVertexBy(self, i, offset):
        self.points[i] = self.points[i] + offset

    def highlightVertex(self, i, action):
        self._highlightIndex = i
        self._highlightMode = action

    def highlightClear(self):
        self._highlightIndex = None

    def copy(self):
        return copy.deepcopy(self)

    def __len__(self):
        return len(self.points)

    def __getitem__(self, key):
        return self.points[key]

    def __setitem__(self, key, value):
        self.points[key] = value
