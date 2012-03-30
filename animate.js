var Animate = (function($) {
  var map;
  var gpx_layer;
  var animate_layer;
  var trackurl;
  var baselayer;

  // http://stackoverflow.com/a/2880929/405240
  var urlparams = {};
  (function () {
    var e,
    a = /\+/g,  // Regex for replacing addition symbol with a space
    r = /([^&=]+)=?([^&]*)/g,
    d = function (s) { return decodeURIComponent(s.replace(a, " ")); },
    q = window.location.search.substring(1);

    while (e = r.exec(q))
      urlparams[d(e[1])] = d(e[2]);
  })();

  trackurl = urlparams.track || "track.gpx";
  baselayer = urlparams.layer || "M";
  zoom = parseInt(urlparams.z) || 14;
  step = parseInt(urlparams.step) || 1000; // number of ms to advance each frame
  interval = parseInt(urlparams.interval) || step; // ms interval between updates
  skip = parseInt(urlparams.skip) || 0;
  embed = urlparams.embed || false;

  var create_gpx_layer = function(name, url) {
    var lgpx = new OpenLayers.Layer.GML(name, url, {
      format: OpenLayers.Format.GPX,
      style: {strokeColor: "green", strokeWidth: 5, strokeOpacity: 0.5},
      projection: new OpenLayers.Projection("EPSG:4326")
    });
    return lgpx;
  };

  var create_animate_layer = function(name, url) {
    var lgpx = new OpenLayers.Layer.Vector.Animate(name, url, {
      strategies: [
        new OpenLayers.Strategy.Fixed(),
        new OpenLayers.Strategy.Animate({
          step: step, interval: interval, skip: skip * 1000
        })
      ],
      protocol: new OpenLayers.Protocol.HTTP({
        url: url,
        format: new OpenLayers.Format.GPX2({
          extractStyles: false, // fixme: probably not used
	  //maxDepth: 2, // fixme: what is this?
          extractAttributes: true,
	  extractTracks: true,
	  extractRoutes: false,
	  extractWaypoints: false
        })
      }),
      style: {strokeColor: "red", strokeWidth: 1, strokeOpacity: 1.0},
      projection: new OpenLayers.Projection("EPSG:4326")
    });

    return lgpx;
  };

  var map_init = function(){
    var layermap = { "M": 0, "C": 1, "G": 3, "Q": 2 };
    gpx_layer = create_gpx_layer("Track", trackurl);
    animate_layer = create_animate_layer("Animation", trackurl);
    map = new OpenLayers.Map("map", {
      controls: [
        new OpenLayers.Control.Navigation()
        //new OpenLayers.Control.PanZoom()
      ],
      layers: [
        new OpenLayers.Layer.OSM.Mapnik("OSM"),
        new OpenLayers.Layer.OSM.CycleMap("Cycle"),
        new OpenLayers.Layer.OSM.MapQuest("MapQuest-OSM"),
        new OpenLayers.Layer.Google("Google Streets",
                                    {numZoomLevels: 20}),
        gpx_layer,
        animate_layer
      ]
    });

    map.setBaseLayer(map.layers[layermap[baselayer] || 0]);

    gpx_layer.events.register('loadend', gpx_layer, function() {
      var bounds = this.getDataExtent();
      //map.zoomToExtent(bounds);   
      map.setCenter(bounds.getCenterLonLat(), zoom);
    });

    animate_layer.events.register('loadend', animate_layer, function() {
      this.setup();
      if (embed) {
        send("loaded");
      } else {
        this.start();
      }
    });

    map.setCenter(
      new OpenLayers.LonLat(4.69005, 50.86739).transform(
        new OpenLayers.Projection("EPSG:4326"),
        map.getProjectionObject()
      ), zoom
    );

    return map;
  };

  var setup_buttons = function() {
    $("#start-btn").click(function(ev) {
      ev.preventDefault();
      animate_layer.start();
    });
    $("#stop-btn").click(function(ev) {
      ev.preventDefault();
      animate_layer.stop();
    });
  };

  var setup_embed = function(embed) {
    if (embed) {
      $("body").children().not(".clipper").hide();
      $(".clipper, body").addClass("embed");
    }
  };

  var setup_size = function(width, height) {
    // normally this is done through css -- but it doesn't seem to
    // work with the embedded webkit -- possibly because resize events
    // aren't sent to webkit

    var diameter = Math.sqrt(width*width + height*height);
    $(".clipper").width(width).height(height);
    $(".rotated")
      .width(diameter).height(diameter)
      .css("left", (width - diameter) / 2 + "px")
      .css("top", (height - diameter) / 2 + "px")
      .css("position", "relative");
  };

  var ready_basic = function() {
    map_init();
    setup_buttons();
    setup_embed(embed);
    setup_size(640, 360);
  };

  var send = function(msg, object) {
    document.title = "null";
    document.title = JSON.stringify({ msg: msg, object: object });
  };

  return {
    ready_basic: ready_basic,
    get_map: function() { return map; },
    start: function() {
      animate_layer.start();
    },
    advance: function() {
      if (!animate_layer.advance()) {
        send("finished");
      } else {
        send("frame");
      }
    }
  };
})(jQuery);

OpenLayers.Layer.Vector.Animate = OpenLayers.Class(OpenLayers.Layer.Vector, {
  initialize: function(name, url, options) {
    var newArguments = [name, options];
    OpenLayers.Layer.Vector.prototype.initialize.apply(this, newArguments);
    this.url = url;
  },

  setup: function() {
    this.strat = this.strategies[1]; // fixme: dumb
    this.strat.time = this.strat.min_time;
    this.strat.time += this.strat.skip;
    this.strat.animate();
  },

  advance: function() {
    var strat = this.strat;
    strat.time += strat.step;
    if (strat.time > strat.max_time) {
      return false;
    } else {
      strat.animate();
      this.map.setCenter(new OpenLayers.LonLat(strat.last_point.x, strat.last_point.y));
      this.set_speed(strat.last_point.attributes.speed);
      this.set_course(strat.last_point.attributes.course);
      return true;
    }
  },

  start: function() {
    var self = this;

    if (this.interval_id) {
      return;
    }

    this.interval_id = window.setInterval(function() {
      if (!self.advance()) {
        self.stop();
      }
    }, this.strat.interval);
  },

  stop: function() {
    if (this.interval_id) {
      window.clearInterval(this.interval_id);
      this.interval_id = null;
    }
  },

  set_speed: function(speed) {
    $("#speed").text(speed + "m/s");
  },

  set_course: function(deg) {
    var rotate = "rotate(" + (-deg) + "deg)";
    $("#map").css({
      "-ms-transform": rotate,
      "-moz-transform": rotate,
      "-webkit-transform": rotate,
      "-o-transform": rotate
    });
  },

  CLASS_NAME: "OpenLayers.Layer.Vector.Animate"
});

OpenLayers.Strategy.Animate = OpenLayers.Class(OpenLayers.Strategy, {

  /**
   * Property: features
   * {Array(<OpenLayers.Feature.Vector>)} Cached features.
   */
  features: null,

  /**
   * Property: animation
   * {Array(<OpenLayers.Feature.Vector>)} What is visible so far.
   */
  animation: null,

  /**
   * APIProperty: rest
   * {Array(<OpenLayers.Feature.Vector>)} Points not yet drawn.
   */
  rest: null,

  /**
   * APIProperty: points
   * {Array(<OpenLayers.Feature.Vector>)} All points
   */
  points: null,

  /**
   * APIProperty: last_point
   * {<OpenLayers.Geometry.Point>} Most recently drawn point
   */
  last_point: null,

  /**
   * Property: animating
   * {Boolean} The strategy is currently animating features.
   */
  animating: false,

  /**
   * Property: step
   * {Integer} The time in ms to advance each frame
   */
  step: 1000, 

  /**
   * Property: interval
   * {Integer} The time in milliseconds between animation updates
   */
  interval: 1000,

  /**
   * Property: skip
   * {Integer} Time in ms at which to begin animation
   */
  skip: 0,

  /**
   * Property: time
   * {Integer} The current animation time.
   */
  time: 0,

  /**
   * Property: min_time
   * {Integer} The start time.
   */
  min_time: 0,

  /**
   * Property: max_time
   * {Integer} The end time.
   */
  max_time: 0,

  /**
   * Constructor: OpenLayers.Strategy.Cluster
   * Create a new clustering strategy.
   *
   * Parameters:
   * options - {Object} Optional object whose properties will be set on the
   *     instance.
   */

  /**
   * APIMethod: activate
   * Activate the strategy.  Register any listeners, do appropriate setup.
   *
   * Returns:
   * {Boolean} The strategy was successfully activated.
   */
  activate: function() {
    var activated = OpenLayers.Strategy.prototype.activate.call(this);
    if(activated) {
      this.layer.events.on({
        "beforefeaturesadded": this.cacheFeatures,
        //"moveend": this.cluster,
        scope: this
      });
    }
    return activated;
  },

  /**
   * APIMethod: deactivate
   * Deactivate the strategy.  Unregister any listeners, do appropriate
   *     tear-down.
   *
   * Returns:
   * {Boolean} The strategy was successfully deactivated.
   */
  deactivate: function() {
    var deactivated = OpenLayers.Strategy.prototype.deactivate.call(this);
    if(deactivated) {
      this.clearCache();
      this.layer.events.un({
        "beforefeaturesadded": this.cacheFeatures,
        //"moveend": this.cluster,
        scope: this
      });
    }
    return deactivated;
  },

  /**
   * Method: cacheFeatures
   * Cache features before they are added to the layer.
   *
   * Parameters:
   * event - {Object} The event that this was listening for.  This will come
   *     with a batch of features to be clustered.
   *
   * Returns:
   * {Boolean} False to stop features from being added to the layer.
   */
  cacheFeatures: function(event) {
    var propagate = true;
    if(!this.animating) {
      var self = this;
      this.clearCache();
      this._init_range();
      this.features = event.features;
      this.last_point = null;
      this.animation = new OpenLayers.Feature.Vector(new OpenLayers.Geometry.LineString([]));

      this.animating = true;
      this.layer.addFeatures(this.animation);
      this.animating = false;

      // btw jQuery.map() flattens 2-d arrays and filters nulls
      this.points = $.map(this.features, function(feature) {
        var components = self.getLineStringComponents(feature);
        if (components) {
          self._update_range(components);
          return components;
        }
        return null;
      });
      this.rest = this.points.slice(0);
      //console.log("min=" + self.min_time + "  max=" + self.max_time);
      this.time = this.min_time;
      this.animate();
      propagate = false;
    }
    return propagate;
  },

      // more or less approximate test
  getLineStringComponents: function(feature) {
    return feature.geometry && feature.geometry.components ? feature.geometry.components : null;
  },

  _init_range: function() {
    this.min_time = this.max_time = undefined;
  },

  _update_range: function(points) {
    var self = this;

    $.each(points, function(i, point) {
      if (point.attributes && point.attributes.time) {
        if (self.min_time === undefined ||
            self.min_time > point.attributes.time) {
          self.min_time = point.attributes.time;
        }
        if (self.max_time === undefined ||
            self.max_time < point.attributes.time) {
          self.max_time = point.attributes.time;
        }
      }
    });
  },


  /**
   * Method: clearCache
   * Clear out the cached features.
   */
  clearCache: function() {
    this.features = null;
  },

  /**
   * Method: animate
   * Filter features based on some time threshold.
   *
   * Parameters:
   * event - {Object} The event received when animate is called as a
   *     result of a moveend event.
   */
  animate: function(event) {
    var new_points = [];
    var self = this;
    var next_point = null;
    var last_point = null;
    var current_index;

    //console.log("animate: " + this.time);

    // points list needs to be sorted by time
    $.each(self.rest, function(i, point) {
      if (point.attributes && point.attributes.time) {
        if (point.attributes.time <= self.time) {
          //console.log("adding point " + point.attributes.time);
          new_points.push(point);
          self.last_point = point;
          last_point = point;
        } else {
          next_point = point;
          return false;
        }
      }
    });

    $.each(new_points, function() {
      self.rest.shift();
    });

    current_index = self.points.length - self.rest.length - 1;

    if (!last_point) {
      var num_points = this.animation.geometry.components.length;
      if (num_points > 0) {
        last_point = this.animation.geometry.components[num_points - 1];
      }
    }

    // check if interpolation needs to be done for next point
    if (next_point && next_point.attributes && next_point.attributes.time &&
        last_point) {
      var delta = next_point.attributes.time - this.time - this.interval;
      if (delta > 0) {
        // linear interpolation
        var f = (this.time - last_point.attributes.time) /
          (next_point.attributes.time - last_point.attributes.time);
        var twerp = last_point.clone();
        //console.log("interpolating " + this.time + " delta=" + delta + " f=" + f);
        //console.log("time=" + this.time + ", last=" + last_point.attributes.time + ", next=" + next_point.attributes.time);
        //console.log("before=" + (last_point.attributes.time - this.time) + " after=" + (next_point.attributes.time - this.time));

        twerp.x += f * (next_point.x - last_point.x);
        twerp.y += f * (next_point.y - last_point.y);
        new_points.push(twerp);
        this.last_point = twerp;
      }
    }

    this.animation.geometry.addComponents(new_points);

    // not sure which method to call for redraw -- go with layer for now
    this.layer.redraw();

    /*
    var feature = new OpenLayers.Feature.Vector(new OpenLayers.Geometry.LineString(valid));
        animation.push(seg);

      var feature = self.features[i];
      if (components) {
        var valid = $.grep(components, function(point) {
          if (point.attributes && point.attributes.time) {
            return point.attributes.time <= self.time;
          } else {
            return true;
          }
        });
        var seg = new OpenLayers.Feature.Vector(new OpenLayers.Geometry.LineString(valid));
        animation.push(seg);
      } else {
        animation.push(feature);
      }
    });

    this.animating = true;
    this.layer.addFeatures(animation);
    this.animating = false;

    this.animation = animation;
    */
  },

  /**
   * Method: createCluster
   * Given a feature, create a cluster.
   *
   * Parameters:
   * feature - {<OpenLayers.Feature.Vector>}
   *
   * Returns:
   * {<OpenLayers.Feature.Vector>} A cluster.
   */
  createCluster: function(feature) {
    var center = feature.geometry.getBounds().getCenterLonLat();
    var cluster = new OpenLayers.Feature.Vector(
      new OpenLayers.Geometry.Point(center.lon, center.lat),
      {count: 1}
    );
    cluster.cluster = [feature];
    return cluster;
  },

  CLASS_NAME: "OpenLayers.Strategy.Animate"
});

/* GPX format modified to extract attributes of each track point */
OpenLayers.Format.GPX2 = OpenLayers.Class(OpenLayers.Format.GPX, {
  /**
   * Method: extractSegment
   *
   * Parameters:
   * segment - {DOMElement} a trkseg or rte node to parse
   * segmentType - {String} nodeName of waypoints that form the line
   *
   * Returns:
   * {<OpenLayers.Geometry.LineString>} A linestring geometry
   */
  extractSegment: function(segment, segmentType) {
    var points = this.getElementsByTagNameNS(segment, segment.namespaceURI, segmentType);
    var point_features = [];
    for (var i = 0, len = points.length; i < len; i++) {
      var point = new OpenLayers.Geometry.Point(points[i].getAttribute("lon"), points[i].getAttribute("lat"));
      if (this.extractAttributes) {
        point.attributes = this.parseAttributes(points[i]);
        point.attributes.time = this.parseTime(point.attributes.time);
        point.attributes.speed = parseFloat(point.attributes.speed);
        point.attributes.course = parseFloat(point.attributes.course);
      }
      point_features.push(point);
    }
    return new OpenLayers.Geometry.LineString(point_features);
  },

  parseTime: function(time) {
    if (time) {
      time = Date.parse(time);
    }
    return time;
  },

  CLASS_NAME: "OpenLayers.Format.GPX2"
});

OpenLayers.Layer.OSM.MapQuest = OpenLayers.Class(OpenLayers.Layer.OSM, {
    /**
     * Constructor: OpenLayers.Layer.OSM.MapQuest
     *
     * Parameters:
     * name - {String}
     * options - {Object} Hashtable of extra options to tag onto the layer
     */
    initialize: function(name, options) {
        var url = [
            "http://otile1.mqcdn.com/tiles/1.0.0/osm/${z}/${x}/${y}.png",
            "http://otile2.mqcdn.com/tiles/1.0.0/osm/${z}/${x}/${y}.png",
            "http://otile3.mqcdn.com/tiles/1.0.0/osm/${z}/${x}/${y}.png",
            "http://otile4.mqcdn.com/tiles/1.0.0/osm/${z}/${x}/${y}.png"
        ];
        options = OpenLayers.Util.extend({
            numZoomLevels: 19,
            buffer: 0,
            transitionEffect: "resize"
        }, options);
        var newArguments = [name, url, options];
        OpenLayers.Layer.OSM.prototype.initialize.apply(this, newArguments);
    },

    CLASS_NAME: "OpenLayers.Layer.OSM.MapQuest"
});


var Youtube = (function() {
  var player;

  var load = function() {
    // 2. This code loads the IFrame Player API code asynchronously.
    var tag = document.createElement('script');
    tag.src = "http://www.youtube.com/player_api";
    var firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
  };

  // 3. This function creates an <iframe> (and YouTube player)
  //    after the API code downloads.
  var api_ready = function() {
    player = new YT.Player('player', {
      height: '390',
      width: '640',
      videoId: 'ttn4TRSlPrs',
      events: {
        'onReady': onPlayerReady,
        'onStateChange': onPlayerStateChange
      }
    });
  };

  // 4. The API will call this function when the video player is ready.
  var onPlayerReady = function(event) {
    event.target.playVideo();
  };

  // 5. The API calls this function when the player's state changes.
  //    The function indicates that when playing a video (state=1),
  //    the player should play for six seconds and then stop.
  var done = false;
  var onPlayerStateChange = function(event) {
    if (event.data == YT.PlayerState.PLAYING && !done) {
      setTimeout(stopVideo, 6000);
      done = true;
    }
  };
  var stopVideo = function() {
    player.stopVideo();
  };

  return {
    load: load,
    api_ready: api_ready
  };
}());

var onYouTubePlayerAPIReady = function() {
  return Youtube.api_ready();
};
