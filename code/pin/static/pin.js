/* Drop-a-pin page. Rules this file keeps (and test_pin.py checks):
   all dynamic text through textContent (the only markup is Leaflet's fixed
   OpenStreetMap attribution), no cookies or
   browser storage, no continuous tracking, and the phone's location is
   only asked for inside the button's click handler. */
(function () {
  "use strict";

  var CENTRE = [50.9097, -1.4044];
  var BOUNDS = [[50.78, -1.65], [51.06, -1.18]];
  var PREVIEW_DELAY_MS = 500;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // The token is the last part of /p/<token>. It never goes in a query string.
  var token = decodeURIComponent(window.location.pathname.split("/").pop() || "");

  var el = {
    app: document.getElementById("app"),
    panel: document.getElementById("panel"),
    status: document.getElementById("status"),
    note: document.getElementById("note"),
    gps: document.getElementById("gpsBtn"),
    submit: document.getElementById("submitBtn"),
    pcForm: document.getElementById("pcForm"),
    pc: document.getElementById("pc"),
    pcBtn: document.getElementById("pcBtn"),
    lock: document.getElementById("lock"),
    lockMsg: document.getElementById("lockMsg")
  };

  var state = { marker: null, circle: null, source: "map", timer: null, seq: 0, locked: false, done: false };

  function say(text, warn) {
    el.status.textContent = text;
    el.status.classList.toggle("warn", Boolean(warn));
  }

  function setNote(text, warn) {
    el.note.textContent = text || "";
    el.note.hidden = !text;
    el.note.classList.toggle("warn", Boolean(warn));
  }

  function setConfirm(on) {
    el.submit.disabled = !on || state.locked || state.done;
  }

  function lockPage(message) {
    state.locked = true;
    clearTimeout(state.timer);
    el.lockMsg.textContent = message || "This link is not working. Reply to our text with the road name instead.";
    el.app.hidden = true;
    el.lock.hidden = false;
  }

  // Every call: POST, JSON, token in the body. Resolves to {status, data}.
  function api(path, extra) {
    var body = { token: token };
    Object.keys(extra || {}).forEach(function (k) { body[k] = extra[k]; });
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "omit",
      cache: "no-store"
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        return { status: res.status, data: data || {} };
      });
    });
  }

  function describe(place) {
    var where = place.street || place.area || "this spot";
    var near = place.landmark || (place.street ? place.area : null);
    var text = where;
    if (near) { text += ", near " + near; }
    if (place.postcode) { text += ", " + place.postcode; }
    return text;
  }

  // ---- Map ---------------------------------------------------------------
  if (typeof L === "undefined") {
    say("The map could not load. Reply to our text with the road name instead.", true);
    return;
  }
  L.Icon.Default.prototype.options.imagePath = "/static/vendor/leaflet/images/";

  var map = L.map("map", {
    center: CENTRE,
    zoom: 14,
    minZoom: 11,
    maxBounds: BOUNDS,
    maxBoundsViscosity: 1.0,
    zoomAnimation: !reduceMotion,
    fadeAnimation: !reduceMotion,
    markerZoomAnimation: !reduceMotion
  });
  map.attributionControl.setPrefix(false);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors"
  }).addTo(map);

  function removeCircle() {
    if (state.circle) { map.removeLayer(state.circle); state.circle = null; }
  }

  function placePin(latlng) {
    if (!state.marker) {
      state.marker = L.marker(latlng, { draggable: true, keyboard: true, title: "Problem location", alt: "Problem location pin" }).addTo(map);
      state.marker.on("dragstart", function () {
        clearTimeout(state.timer);
        setConfirm(false);
        say("Move the pin, then let go.");
      });
      state.marker.on("dragend", function () {
        // A hand-placed pin is the resident's own choice, not the phone's reading.
        state.source = "map";
        removeCircle();
        setNote("");
        schedulePreview();
      });
    } else {
      state.marker.setLatLng(latlng);
    }
  }

  function schedulePreview() {
    setConfirm(false);
    say("Finding the street.");
    clearTimeout(state.timer);
    state.timer = setTimeout(runPreview, PREVIEW_DELAY_MS);
  }

  function runPreview() {
    if (!state.marker || state.locked) { return; }
    var mine = ++state.seq;
    var ll = state.marker.getLatLng();
    api("/api/preview", { lat: ll.lat, lng: ll.lng }).then(function (res) {
      if (mine !== state.seq) { return; } // a newer pin position won
      var d = res.data;
      if (res.status === 200) {
        if (d.coverage === "unverified") {
          say("Pin set: " + describe(d) + ". We could not confirm this is in Southampton, so an officer will check it.", true);
        } else {
          say("Pin set: " + describe(d) + ".");
        }
        setConfirm(true);
      } else if (res.status === 404 || res.status === 410) {
        lockPage(d.error);
      } else if (res.status === 422) {
        say(d.error || "That spot is outside Southampton.", true);
        setConfirm(false);
      } else if (res.status === 429) {
        say(d.error || "Too many tries. Please wait a minute.", true);
      } else {
        say("We could not check that spot. Move the pin a little to try again.", true);
      }
    }).catch(function () {
      if (mine === state.seq) { say("We could not reach the server. Check your connection and try again.", true); }
    });
  }

  map.on("click", function (e) {
    if (state.locked || state.done) { return; }
    state.source = "map";
    removeCircle();
    setNote("");
    placePin(e.latlng);
    schedulePreview();
  });

  // ---- Phone location: opt-in, one reading, only on this button press ----
  el.gps.addEventListener("click", function () {
    if (state.locked || state.done) { return; }
    if (!("geolocation" in navigator)) {
      say("Your phone did not share a location. Tap the map where the problem is instead.");
      return;
    }
    say("Asking your phone for its location.");
    navigator.geolocation.getCurrentPosition(onPosition, onPositionError,
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  });

  function onPosition(pos) {
    var ll = L.latLng(pos.coords.latitude, pos.coords.longitude);
    var accuracy = Math.max(1, Math.round(pos.coords.accuracy || 0));
    state.source = "gps";
    placePin(ll);
    removeCircle();
    state.circle = L.circle(ll, { radius: accuracy, interactive: false, weight: 1 }).addTo(map);
    map.setView(ll, 17, { animate: !reduceMotion });
    var text = "This is where you are now (within about " + accuracy + " m). If the problem is somewhere else, drag the pin.";
    if (accuracy > 100) {
      setNote(text + " Your phone's reading is not very precise, so please check the pin.", true);
    } else {
      setNote(text);
    }
    schedulePreview();
  }

  function onPositionError(err) {
    if (err && err.code === 1) {
      say("No problem. Tap the map where the problem is instead.");
    } else {
      say("We could not get your phone's location. Tap the map where the problem is instead.");
    }
  }

  // ---- Postcode search ---------------------------------------------------
  el.pcForm.addEventListener("submit", function (e) {
    e.preventDefault();
    if (state.locked || state.done) { return; }
    var value = el.pc.value.trim();
    if (!value) { say("Type a postcode, or tap the map."); el.pc.focus(); return; }
    el.pcBtn.disabled = true;
    say("Looking up that postcode.");
    api("/api/postcode", { postcode: value }).then(function (res) {
      var d = res.data;
      if (res.status === 200) {
        var ll = L.latLng(d.lat, d.lng);
        state.source = "postcode";
        removeCircle();
        setNote("We put the pin in the middle of that postcode. Drag it to the exact spot if you can.");
        placePin(ll);
        map.setView(ll, 17, { animate: !reduceMotion });
        schedulePreview();
      } else if (res.status === 404 || res.status === 410) {
        lockPage(d.error);
      } else {
        say(d.error || "We could not find that postcode. Tap the map instead.", true);
      }
    }).catch(function () {
      say("We could not reach the server. Check your connection and try again.", true);
    }).then(function () {
      el.pcBtn.disabled = false;
    });
  });

  // ---- Confirm -----------------------------------------------------------
  el.submit.addEventListener("click", function () {
    if (!state.marker || state.locked || state.done) { return; }
    var ll = state.marker.getLatLng();
    setConfirm(false);
    say("Saving.");
    api("/api/confirm", { lat: ll.lat, lng: ll.lng, source: state.source }).then(function (res) {
      var d = res.data;
      if (res.status === 200) {
        showThanks(d.saved || {}, d.change_minutes || 10);
      } else if (res.status === 404 || res.status === 410) {
        lockPage(d.error);
      } else if (res.status === 422) {
        say(d.error || "That spot is outside Southampton.", true);
      } else {
        say("That did not save. Please try again.", true);
        setConfirm(true);
      }
    }).catch(function () {
      say("That did not save. Check your connection and try again.", true);
      setConfirm(true);
    });
  });

  function showThanks(saved, minutes) {
    state.done = true;
    if (state.marker) { state.marker.dragging.disable(); }
    var panel = el.panel;
    while (panel.firstChild) { panel.removeChild(panel.firstChild); }

    var box = document.createElement("div");
    box.className = "thanks";
    box.setAttribute("role", "status");
    var h = document.createElement("h2");
    h.textContent = "Thank you";
    var where = document.createElement("p");
    where.textContent = "We have logged the problem at " + describe(saved) + ".";
    var change = document.createElement("p");
    change.className = "hint";
    change.textContent = "You can change the pin for the next " + minutes + " minutes.";
    var again = document.createElement("button");
    again.type = "button";
    again.className = "secondary";
    again.textContent = "Change the pin";
    again.addEventListener("click", function () { window.location.reload(); });

    box.appendChild(h);
    box.appendChild(where);
    box.appendChild(change);
    box.appendChild(again);
    panel.appendChild(box);
    h.setAttribute("tabindex", "-1");
    h.focus();
  }

  // ---- On load: is this link still live? ----------------------------------
  api("/api/check", {}).then(function (res) {
    if (res.status === 200) {
      say("Tap the map where the problem is.");
    } else {
      lockPage(res.data.error);
    }
  }).catch(function () {
    say("We could not reach the server. Check your connection and reload the page.", true);
  });
})();
