/* Drop-a-pin page. Rules this file keeps (and test_pin.py checks):
   all dynamic text through textContent (the only markup is Leaflet's fixed
   OpenStreetMap attribution), no cookies or browser storage, no continuous
   tracking, and the phone's location is only asked for inside the button's
   click handler.

   Three ways to say where, like the council's own form:
     1. "Use my current location": one reading, only when the button is pressed
     2. search: every Southampton street, filtered on this phone as you type,
        so what you type never leaves it; Find also takes a postcode or a place
     3. the map: the pin is fixed in the middle and the resident moves the map
        under it, by touch, mouse or arrow keys. The pin lifts while the map
        moves and drops when it stops. The location is always the map's centre. */
(function () {
  "use strict";

  var CENTRE = [50.9097, -1.4044];
  var BOUNDS = [[50.78, -1.65], [51.06, -1.18]];
  var PREVIEW_DELAY_MS = 500;
  var STREET_ZOOM = 17;
  var MAX_SUGGESTIONS = 8;
  var POSTCODE = /^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$/;
  // Same canonical short forms as geo/southampton.py, so "Lawn Rd" finds "Lawn Road".
  var SHORT = {
    road: "rd", street: "st", saint: "st", avenue: "ave", av: "ave", lane: "ln", close: "cl",
    drive: "dr", crescent: "cres", cr: "cres", gardens: "gdns", garden: "gdns", gdn: "gdns",
    place: "pl", square: "sq", terrace: "tce", terr: "tce", court: "ct", grove: "gr", gro: "gr",
    park: "pk", hill: "hl", way: "wy", parade: "pde", mews: "mws", walk: "wk", highway: "hwy",
    roundabout: "rdbt", north: "n", nth: "n", south: "s", sth: "s", east: "e", west: "w"
  };
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // The token is the last part of /p/<token>. It never goes in a query string.
  var token = decodeURIComponent(window.location.pathname.split("/").pop() || "");

  var el = {
    app: document.getElementById("app"),
    title: document.getElementById("title"),
    panel: document.getElementById("panel"),
    status: document.getElementById("status"),
    note: document.getElementById("note"),
    gps: document.getElementById("gpsBtn"),
    submit: document.getElementById("submitBtn"),
    form: document.getElementById("pcForm"),
    query: document.getElementById("pc"),
    find: document.getElementById("pcBtn"),
    results: document.getElementById("results"),
    mapWrap: document.getElementById("mapWrap"),
    lock: document.getElementById("lock"),
    lockMsg: document.getElementById("lockMsg")
  };

  // touched: the resident has chosen a spot at least once, so the default
  // city-centre view can never be confirmed by accident.
  // auto: the map is moving because we moved it (search, phone reading).
  var state = { circle: null, source: "map", timer: null, seq: 0, touched: false, auto: false,
                locked: false, done: false, streets: null, loading: null, options: [], active: -1 };

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
    el.submit.disabled = !on || !state.touched || state.locked || state.done;
  }

  function clearResults() {
    while (el.results.firstChild) { el.results.removeChild(el.results.firstChild); }
    el.results.hidden = true;
    el.query.setAttribute("aria-expanded", "false");
    el.query.removeAttribute("aria-activedescendant");
    state.options = [];
    state.active = -1;
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
    keyboard: true,          // arrow keys pan, + and - zoom: the pin follows the centre
    keyboardPanDelta: 60,
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

  // The pin lifts while the map moves and drops when it stops.
  function dropPin() {
    el.mapWrap.classList.remove("dropped");
    void el.mapWrap.offsetWidth; // restart the animation
    el.mapWrap.classList.add("dropped");
  }
  el.mapWrap.addEventListener("animationend", function () { el.mapWrap.classList.remove("dropped"); });

  // Our own moves are synchronous (no animation), so the flag is exact.
  function moveTo(latlng, zoom) {
    state.auto = true;
    map.setView(latlng, zoom, { animate: false });
    state.auto = false;
    dropPin();
  }

  map.on("movestart", function () {
    if (state.locked || state.done) { return; }
    el.mapWrap.classList.add("moving");
    clearTimeout(state.timer);
    setConfirm(false);
    if (!state.auto) {
      // The resident moved the map: the spot is now their own choice.
      state.source = "map";
      removeCircle();
      setNote("");
    }
  });

  map.on("moveend", function () {
    el.mapWrap.classList.remove("moving");
    if (state.locked || state.done) { return; }
    if (!state.auto) { state.touched = true; dropPin(); }
    if (state.touched) { schedulePreview(); }
  });

  map.on("click", function (e) {
    if (state.locked || state.done) { return; }
    state.touched = true;
    state.source = "map";
    removeCircle();
    setNote("");
    clearResults();
    map.panTo(e.latlng, { animate: !reduceMotion });
    dropPin();
    schedulePreview(); // also covers a tap right on the pin, where the map does not move
  });

  function schedulePreview() {
    setConfirm(false);
    say("Finding the street.");
    clearTimeout(state.timer);
    state.timer = setTimeout(runPreview, PREVIEW_DELAY_MS);
  }

  function runPreview() {
    if (state.locked || state.done) { return; }
    var mine = ++state.seq;
    var ll = map.getCenter();
    api("/api/preview", { lat: ll.lat, lng: ll.lng }).then(function (res) {
      if (mine !== state.seq) { return; } // a newer map position won
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
        say("We could not check that spot. Move the map a little to try again.", true);
      }
    }).catch(function () {
      if (mine === state.seq) { say("We could not reach the server. Check your connection and try again.", true); }
    });
  }

  // ---- 1. Phone location: opt-in, one reading, only on this button press --
  el.gps.addEventListener("click", function () {
    if (state.locked || state.done) { return; }
    if (!("geolocation" in navigator)) {
      say("Your phone did not share a location. Search for the street or move the map instead.");
      return;
    }
    say("Asking your phone for its location.");
    el.gps.disabled = true;
    navigator.geolocation.getCurrentPosition(onPosition, onPositionError,
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  });

  function onPosition(pos) {
    el.gps.disabled = false;
    var ll = L.latLng(pos.coords.latitude, pos.coords.longitude);
    var accuracy = Math.max(1, Math.round(pos.coords.accuracy || 0));
    clearResults();
    removeCircle();
    state.touched = true;
    moveTo(ll, STREET_ZOOM);
    state.source = "gps";
    state.circle = L.circle(ll, { radius: accuracy, interactive: false, weight: 1 }).addTo(map);
    var text = "This is where you are now (within about " + accuracy + " m). If the problem is somewhere else, move the map.";
    if (accuracy > 100) {
      setNote(text + " Your phone's reading is not very precise, so please check the pin.", true);
    } else {
      setNote(text);
    }
    schedulePreview();
  }

  function onPositionError(err) {
    el.gps.disabled = false;
    if (err && err.code === 1) {
      say("No problem. Search for the street, or move the map to the problem instead.");
    } else if (!window.isSecureContext) {
      say("Your phone only shares its location on a secure page. Search for the street or move the map instead.");
    } else {
      say("We could not get your phone's location. Search for the street or move the map instead.");
    }
  }

  // ---- 2. Search: streets as you type, then postcode or place on Find ------
  function goTo(latlng, source, note) {
    clearResults();
    removeCircle();
    state.touched = true;
    moveTo(latlng, STREET_ZOOM);
    state.source = source;
    setNote(note);
    schedulePreview();
  }

  function normalise(text) {
    var words = String(text || "").toLowerCase().replace(/['’]/g, "").match(/[a-z0-9]+/g) || [];
    return words.map(function (w) { return SHORT[w] || w; }).join(" ");
  }

  // The street list loads the first time someone uses the search box, not before.
  function loadStreets() {
    if (state.streets || state.loading) { return state.loading; }
    state.loading = fetch("/static/streets.json", { credentials: "omit" })
      .then(function (res) { return res.ok ? res.json() : { streets: [] }; })
      .then(function (data) {
        state.streets = (data.streets || []).map(function (s) {
          return { name: s[0], area: s[1], lat: s[2], lng: s[3], key: normalise(s[0]) };
        });
        return state.streets;
      })
      .catch(function () { state.streets = []; return state.streets; });
    return state.loading;
  }

  function matchStreets(query) {
    var q = normalise(query);
    if (q.length < 2 || !state.streets) { return []; }
    var found = [];
    state.streets.forEach(function (s) {
      var rank = s.key.indexOf(q) === 0 ? 0 : (" " + s.key).indexOf(" " + q) >= 0 ? 1 : s.key.indexOf(q) >= 0 ? 2 : -1;
      if (rank >= 0) { found.push({ rank: rank, street: s }); }
    });
    found.sort(function (a, b) {
      return a.rank - b.rank || a.street.name.localeCompare(b.street.name) || a.street.area.localeCompare(b.street.area);
    });
    return found.slice(0, MAX_SUGGESTIONS).map(function (f) { return f.street; });
  }

  function chooseStreet(s) {
    el.query.value = s.name;
    goTo(L.latLng(s.lat, s.lng), "map", "We put the pin on " + s.name + ". Move the map to the exact spot if you can.");
    map.getContainer().focus();
  }

  function setActive(index) {
    state.active = index;
    Array.prototype.forEach.call(el.results.children, function (li, i) {
      li.setAttribute("aria-selected", i === index ? "true" : "false");
      li.classList.toggle("active", i === index);
    });
    if (index >= 0 && el.results.children[index]) {
      el.query.setAttribute("aria-activedescendant", el.results.children[index].id);
      el.results.children[index].scrollIntoView({ block: "nearest" });
    } else {
      el.query.removeAttribute("aria-activedescendant");
    }
  }

  function showStreets(streets) {
    clearResults();
    state.options = streets;
    streets.forEach(function (s, i) {
      var li = document.createElement("li");
      li.id = "street-" + i;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", "false");
      var name = document.createElement("span");
      name.className = "opt-name";
      name.textContent = s.name;
      li.appendChild(name);
      if (s.area) {
        var area = document.createElement("span");
        area.className = "opt-area";
        area.textContent = s.area;
        li.appendChild(area);
      }
      // pointerdown, not click: the input's blur must not close the list first.
      li.addEventListener("pointerdown", function (e) { e.preventDefault(); chooseStreet(s); });
      el.results.appendChild(li);
    });
    el.results.hidden = streets.length === 0;
    el.query.setAttribute("aria-expanded", streets.length ? "true" : "false");
  }

  // Places from the search service (a landmark, a building): buttons, picked once.
  function showPlaces(results) {
    clearResults();
    results.forEach(function (r) {
      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = r.label;
      btn.addEventListener("click", function () {
        goTo(L.latLng(r.lat, r.lng), "map", "Move the map if the problem is not right under the pin.");
        map.getContainer().focus();
      });
      li.appendChild(btn);
      el.results.appendChild(li);
    });
    el.results.hidden = results.length === 0;
    say(results.length === 1 ? "Found 1 place. Pick it below." : "Found " + results.length + " places. Pick one below.");
  }

  el.query.addEventListener("focus", loadStreets);
  el.query.addEventListener("input", function () {
    var value = el.query.value;
    loadStreets().then(function () {
      if (el.query.value !== value) { return; } // a newer keystroke won
      var asPostcode = value.toUpperCase().trim().replace(/\s+/g, " ");
      if (POSTCODE.test(asPostcode)) { clearResults(); return; }
      showStreets(matchStreets(value));
    });
  });
  el.query.addEventListener("keydown", function (e) {
    var count = state.options.length;
    if (e.key === "ArrowDown" && count) {
      e.preventDefault();
      setActive((state.active + 1) % count);
    } else if (e.key === "ArrowUp" && count) {
      e.preventDefault();
      setActive(state.active <= 0 ? count - 1 : state.active - 1);
    } else if (e.key === "Enter" && state.active >= 0 && state.options[state.active]) {
      e.preventDefault();
      chooseStreet(state.options[state.active]);
    } else if (e.key === "Escape") {
      clearResults();
    }
  });
  el.query.addEventListener("blur", function () {
    // Let a tap on a suggestion land first.
    setTimeout(function () { if (document.activeElement !== el.query) { clearResults(); } }, 150);
  });

  el.form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (state.locked || state.done) { return; }
    var value = el.query.value.trim();
    if (!value) { say("Type a postcode, street or place, or move the map."); el.query.focus(); return; }
    var asPostcode = value.toUpperCase().replace(/\s+/g, " ");
    var isPostcode = POSTCODE.test(asPostcode);
    if (!isPostcode) {
      // A street we know: straight there, no lookup.
      var streets = matchStreets(value);
      if (streets.length && normalise(streets[0].name) === normalise(value)) { chooseStreet(streets[0]); return; }
      if (streets.length) { showStreets(streets); say("Pick your street below."); return; }
    }
    el.find.disabled = true;
    clearResults();
    say(isPostcode ? "Looking up that postcode." : "Searching Southampton.");
    var call = isPostcode ? api("/api/postcode", { postcode: value }) : api("/api/search", { query: value });
    call.then(function (res) {
      var d = res.data;
      if (res.status === 200 && isPostcode) {
        goTo(L.latLng(d.lat, d.lng), "postcode",
          "We put the pin in the middle of that postcode. Move the map to the exact spot if you can.");
      } else if (res.status === 200) {
        showPlaces(d.results || []);
      } else if (res.status === 404 || res.status === 410) {
        lockPage(d.error);
      } else {
        say(d.error || "We could not find that. Move the map instead.", true);
      }
    }).catch(function () {
      say("We could not reach the server. Check your connection and try again.", true);
    }).then(function () {
      el.find.disabled = false;
    });
  });

  // ---- Confirm -----------------------------------------------------------
  el.submit.addEventListener("click", function () {
    if (!state.touched || state.locked || state.done) { return; }
    var ll = map.getCenter();
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
    // Freeze the map so the pin shows exactly what was saved.
    [map.dragging, map.keyboard, map.scrollWheelZoom, map.doubleClickZoom, map.touchZoom, map.boxZoom]
      .forEach(function (handler) { if (handler) { handler.disable(); } });
    clearResults();
    var panel = el.panel;
    while (panel.firstChild) { panel.removeChild(panel.firstChild); }

    var box = document.createElement("div");
    box.className = "thanks";
    box.setAttribute("role", "status");
    var h = document.createElement("h2");
    h.textContent = "Thank you";
    var where = document.createElement("p");
    where.textContent = "We have logged the problem at " + describe(saved) + ".";
    var back = document.createElement("p");
    back.textContent = "We have added it to your report and texted you to confirm. You can close this page.";
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
    box.appendChild(back);
    box.appendChild(change);
    box.appendChild(again);
    panel.appendChild(box);
    h.setAttribute("tabindex", "-1");
    h.focus();
  }

  // ---- On load: is this link still live, and what is it about? ------------
  api("/api/check", {}).then(function (res) {
    if (res.status === 200) {
      if (res.data.what) {
        el.title.textContent = "Where is the " + res.data.what + "?";
        document.title = el.title.textContent;
      }
      say("Use your location, search for the street, or move the map so the pin sits on the problem.");
    } else {
      lockPage(res.data.error);
    }
  }).catch(function () {
    say("We could not reach the server. Check your connection and reload the page.", true);
  });
})();
