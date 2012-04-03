#!/usr/bin/env python

import sys
import os.path
import json
import urllib
import re
from optparse import OptionParser

__VERSION__ = "0.5"

def parse_options():
    usage = "usage: %prog [options] INFILE.gpx"
    desc = "Converts a GPX file into a slippy map animation."

    parser = OptionParser(usage=usage, description=desc,
                          version="%%prog %s" % __VERSION__)
    parser.add_option("-o", "--output", dest="outfile",
                      help="write video to FILE (default INFILE.ogg)",
                      metavar="FILE", action="store", type="string")
    parser.add_option("-r", "--framerate", dest="framerate",
                      help="output video framerate (e.g. use 30000/1001 for NTSC, 25.0 for PAL, default=%default)",
                      metavar="RATE", default="30000/1001",
                      action="store", type="string")
    parser.add_option("-s", "--speedup", dest="speedup",
                      help="speed-up factor (default %default)",
                      default="2.0", action="store", type="float")
    parser.add_option("--width", dest="width",
                      help="animation width (default %default)",
                      default=640, action="store", type="int")
    parser.add_option("--height", dest="height",
                      help="animation height (default %default)",
                      default=360, action="store", type="int")
    parser.add_option("-z", "--zoom", dest="zoom",
                      help="map zoom (default %default)",
                      default=16, action="store", type="int")

    parser.add_option("--osm", dest="use_osm",
                      help="Use OpenStreetMap Mapnik as the base layer (default)",
                      default=False, action="store_true")
    parser.add_option("--google-street", dest="use_google",
                      help="Use Google Maps as the base layer",
                      default=False, action="store_true")
    parser.add_option("--mapquest", dest="use_mapquest",
                      help="Use MapQuest Open as the base layer",
                      default=False, action="store_true")
    parser.add_option("--cycle", dest="use_cycle",
                      help="Use OpenCycleMap as the base layer",
                      default=False, action="store_true")
    parser.add_option("-c", "--track-colour", dest="track_colour",
                      help="track colour (HTML format, default %default)",
                      default="red", action="store", type="string")
    parser.add_option("--track-opacity", dest="track_opacity",
                      help="track colour (HTML format)", default=0.6,
                      action="store", type="float")
    parser.add_option("--track-width", dest="track_width",
                      help="track width in pixels", default=5.0,
                      action="store", type="float")
    parser.add_option("--pilot-colour", dest="pilot_colour",
                      help="pilot colour (HTML format)", default="red",
                      action="store", type="string")
    parser.add_option("--pilot-opacity", dest="pilot_opacity",
                      help="pilot colour (HTML format)", default=0.6,
                      action="store", type="float")
    parser.add_option("--pilot-width", dest="pilot_width",
                      help="pilot width in pixels", default=5.0,
                      action="store", type="float")
    parser.add_option("-p", "--pilot",
                      action="store_true", dest="pilot", default=False,
                      help="draw a pilot track before the animation")
    parser.add_option("-q", "--quiet",
                      action="store_false", dest="verbose", default=True,
                      help="don't print status messages to stdout")

    (options, args) = parser.parse_args()

    if len(args) == 0:
        parser.print_help()
        sys.exit(0)
    if len(args) > 1:
        parser.error("You must specify a single input GPX file")

    options.gpx_file = args[0]
    options.outfile = options.outfile or options_outfilename(options.gpx_file)
    options.base_layer = options_check_base_layer(parser, options)
    options.framerate_float = options_parse_framerate(parser, options.framerate)

    print "options are: %s" % str(options)
    return options

def options_outfilename(infilename):
    root, ext = os.path.splitext(infilename)
    return "%s.ogg" % root

def options_check_base_layer(parser, options):
    default = "M"
    base_layer = None
    mapping = { "osm": "M", "google": "G", "mapquest": "Q", "cycle": "C" }
    for mapname, code in mapping.iteritems():
        if getattr(options, "use_%s" % mapname):
            if base_layer is None:
                base_layer = code
            else:
                parser.error("You can only specify a single base layer")
    return base_layer or default

def options_parse_framerate(parser, frameratestr):
    m = re.match(r"([0-9]*\.?[0-9]*)(?:/([0-9]*\.?[0-9]*))?", frameratestr)
    if m:
        top = float(m.group(1))
        bottom = float(m.group(2) or 1.0)
        return top / bottom
    parser.error("Incorrect framerate specification \"%s\"" % frameratestr)

options = parse_options()

# import gst and gtk after option parsing because they like to steal argv
import gobject
import gtk
import pango
import webkit
import pygst
pygst.require('0.10')
import gst

class MapWindow(gtk.Window):

    def __init__(self, options):
        gtk.Window.__init__(self)

        self.width = options.width
        self.height = options.height
        self.framerate = options.framerate_float
        self.speedup = options.speedup

        self.frame_num = 0

        view = webkit.WebView()

        # needed to load other resources
        settings = view.get_settings()
        settings.set_property('enable-file-access-from-file-uris', 1)

        #view.connect("hovering-over-link", self._hovering_over_link_cb)
        view.connect("load-finished", self._view_load_finished_cb)
        view.connect("title-changed", self._title_changed_cb)

        view.set_size_request(self.width, self.height)

        alignment = gtk.Alignment(0.0, 0.0, 0.0, 0.0)
        alignment.add(view)
        self.add(alignment)

        #vbox = gtk.VBox(spacing=1)
        #vbox.pack_start(toolbar, expand=False, fill=False)
        #vbox.pack_start(content_tabs)
        #self.add(vbox)

        self.connect('destroy', destroy_cb)

        self.show_all()

        self.pipeline, self.snapsrc = gst_pipeline(view, options.outfile,
                                                   options.framerate)

        path = os.path.abspath(os.path.dirname(__file__))
        loc = "file://%s/gpxanim.html" % path
        args = {
            "embed": 1,
            "track": options.gpx_file,
            "layer": options.base_layer,
            "z": options.zoom,
            "step": self.speedup * 1000.0 / self.framerate,
            "width": self.width,
            "height": self.height,
            "pilot": "1" if options.pilot else "0",
            "track_colour": options.track_colour,
            "track_width": options.track_width,
            "track_opacity": options.track_opacity,
            "pilot_colour": options.pilot_colour,
            "pilot_width": options.pilot_width,
            "pilot_opacity": options.pilot_opacity,
            }
        uri = "%s?%s" % (loc, urllib.urlencode(args))
        print "loading: %s" % uri
        view.load_uri(uri)

    def _view_load_finished_cb(self, view, frame):
        # title = frame.get_title()
        # if not title:
        #     title = frame.get_uri()
        # self.set_title("PyWebKitGtk - %s" % title)
        self.set_title("Converter")

    def _title_changed_cb(self, view, frame, title):
        #self._view_load_finished_cb(view, frame)
        try:
            msg = json.loads(frame.get_title())
        except ValueError:
            msg = None
        if msg:
            f = getattr(self, "_msg_%s" % msg["msg"], None)
            if f:            
                args = msg.get("object", {})
                f(view, **args)
            else:
                print "*** bugger: couldn't call %s" % msg["msg"]

    def execute(self, view, script, timeout=None):
        def idle_execute_script():
            view.execute_script(script)
        if timeout is None:
            gobject.idle_add(idle_execute_script)
        else:
            gobject.timeout_add(timeout, idle_execute_script)

    def _msg_loaded(self, view):
        print "loaded"
        self.execute(view, "console.log('hello, world!');")
        def begin():
            self.execute(view, "Animate.advance();")
        #gobject.timeout_add(2000, begin)
        begin()

    def _msg_frame(self, view):
        #print "Frame %d" % self.frame_num
        self.get_screenshot(view, self.frame_num * 1000 / self.framerate)
        self.frame_num += 1
        self.execute(view, "Animate.advance();", 100)

    def _msg_finished(self, view):
        print "finished"
        self.pipeline.set_state(gst.STATE_NULL)
        destroy_cb(self)

    def get_screenshot(self, widget, time_ms):
        if widget.get_realized():
            snapshot = widget.get_snapshot()
            w, h = snapshot.get_size()
            pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, w, h)
            pixbuf.get_from_drawable(snapshot, widget.get_colormap(),
                                     0, 0, 0, 0, w, h)
            #pixbuf.save(self.frame_filename(frame_num), "png")
            self.snapsrc.add_snapshot(pixbuf, time_ms)

    @staticmethod
    def frame_filename(frame_num):
        if frame_num is None:
            return "frame.png"
        else:
            return "frame%05d.png" % frame_num

def load_requested_cb (widget, text, content_pane):
    if not text:
        return
    content_pane.load(text)

def destroy_cb(window):
    """destroy window resources"""
    window.pipeline.set_state(gst.STATE_NULL)
    window.destroy()
    gtk.main_quit()

class SnapshotSource(gst.Element):
    __gstdetails__ = (
        "SnapshotSource plugin",
        "convert.py",
        "A source of screenshot video frames",
        "Rodney Lorrimar <rodney@rodney.id.au>")

    _src_template = gst.PadTemplate("src",
                                    gst.PAD_SRC,
                                    gst.PAD_ALWAYS,
                                    gst.caps_new_any())

    __gsttemplates__ = (_src_template, )

    def __init__(self, framerate=None):
        gst.Element.__init__ (self)
        self.framerate = framerate
        self.src_pad = gst.Pad(self._src_template)
        self.src_pad.use_fixed_caps()
        self.add_pad(self.src_pad)
 
    def nonono__init__(self, widget):   
        #initialise parent class
        #gst.Element.__init__(self, *args, **kwargs)
        self.__gobject_init__()

        self.widget = widget

        # #source pad, outgoing data
        # self.srcpad = gst.Pad(self._srctemplate)
        # self.srcpad.set_setcaps_function(self._src_setcaps)
        # self.srcpad.set_chain_function(self._src_chain)
        
        # #sink pad, incoming data
        # #self.sinkpad = gst.Pad(self._sinktemplate)
        
        # #make pads available
        # self.add_pad(self.srcpad)
        # #self.add_pad(self.sinkpad)

    def add_snapshot(self, pixbuf, time_ms):
        self.width = pixbuf.get_width()
        self.height = pixbuf.get_height()
        #print "Pushing %dx%d snapshot to source" % (self.width, self.height)
        buf = gst.Buffer(pixbuf.get_pixels())
        buf.timestamp = int(round(time_ms * gst.MSECOND))
        # Don't forget to set the right caps on the buffer
        self.set_caps_on(buf)
        src = self.get_static_pad("src")
        status = src.push(buf)
        if status != gst.FLOW_OK:
            raise RuntimeError, "Error while pushing buffer : " + str(status)

    def set_caps_on(self, dest):
        """Set the current frame caps on the specified object"""
        framerate = ("framerate=%s," % self.framerate) if self.framerate else ""

        # The data is always native-endian xRGB; ffmpegcolorspace
        # doesn't support little-endian xRGB, but does support
        # big-endian BGRx.
        caps = gst.caps_from_string("video/x-raw-rgb,bpp=24,depth=24,\
                                     red_mask=0xff0000,\
                                     green_mask=0x00ff00,\
                                     blue_mask=0x0000ff,\
                                     endianness=4321,\
                                     %swidth=%d,height=%d" \
                                        % (framerate, self.width, self.height))
        if dest:
            dest.set_caps(caps)

    def _src_setcaps(self, pad, caps):
        #we negotiate our capabilities here, this function is called
        #as autovideosink accepts anything, we just say yes we can handle the
        #incoming data
        return True
    
    def _src_chain(self, pad, buf):
        #this is where we do filtering
        #and then push a buffer to the next element, returning a value saying
        # it was either successful or not.
        return self.srcpad.push(buf)

#here we register our class with glib, the c-based object system used by
#gstreamer
gobject.type_register(SnapshotSource)

def gst_pipeline(widget, outfile=None, framerate=None):
    ## this code creates the following pipeline, equivalent to 
    ## gst-launch-0.10 SnapshotSource  ! videoscale ! ffmpegcolorspace ! autovideosink

    # first create individual gstreamer elements

    snapsrc = SnapshotSource(framerate)
    vscale = gst.element_factory_make("videoscale")
    cspace = gst.element_factory_make("ffmpegcolorspace")

    elements = [snapsrc, vscale, cspace]

    if outfile:
        print "recording to %s" % outfile
        videorate = gst.element_factory_make("videorate")
        theoraenc = gst.element_factory_make("theoraenc")
        oggmux = gst.element_factory_make("oggmux")
        filesink = gst.parse_launch ("filesink location=%s" % outfile)
        if not filesink:
            raise RuntimeError, "Can't create filesink element"
        elements.extend([videorate, theoraenc, oggmux, filesink])
    else:
        vsink = gst.element_factory_make("autovideosink")
        elements.append(vsink)

    # create the pipeline
    p = gst.Pipeline()
    p.add(*elements)
    gst.element_link_many(*elements)

    # set pipeline to playback state
    p.set_state(gst.STATE_PLAYING)

    return p, snapsrc

if __name__ == "__main__":
    window = MapWindow(options)
    gtk.main()
