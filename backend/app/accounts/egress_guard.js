(function () {
  'use strict';
  if (window.__MIRROR_EGRESS_GUARD__) { return; }
  window.__MIRROR_EGRESS_GUARD__ = true;

  // 镜像页面外联泄漏防护：除镜像自身与下方白名单外，拦截一切跨源请求，
  // 防止未被网关重写的官方/遥测端点（arkose、sentry、statsig、cdn.oaistatic.com 等）
  // 从用户浏览器直连并暴露真实 IP 与设备指纹。拦截结果聚合上报到访问日志。
  var BUILTIN_HOSTS = ['challenges.cloudflare.com'];
  var EXTRA_HOSTS = __MIRROR_TRUSTED_HOSTS__;
  var REPORT_URL = '/0x/user/egress-report';
  var MAX_PENDING = 100;
  var FLUSH_MS = 3000;

  var allowHosts = {};
  BUILTIN_HOSTS.concat(EXTRA_HOSTS || []).forEach(function (host) {
    host = String(host || '').toLowerCase().replace(/^\*\./, '');
    if (host) { allowHosts[host] = true; }
  });

  function isAllowedUrl(url) {
    try {
      url = String(url == null ? '' : url).trim();
      if (!url || url.charAt(0) === '#') { return true; }
      if (/^(data|blob|about|javascript|mailto|tel|sms):/i.test(url)) { return true; }
      var parsed = new URL(url, location.href);
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:' ||
          parsed.protocol === 'ws:' || parsed.protocol === 'wss:') {
        return parsed.host === location.host || allowHosts[parsed.hostname.toLowerCase()] === true;
      }
      return false;
    } catch (error) {
      return true;
    }
  }

  var warned = {};
  var pending = {};
  var pendingCount = 0;
  var flushTimer = null;

  function report(url, kind) {
    try {
      url = String(url == null ? '' : url);
      if (url.length > 500) { url = url.slice(0, 500); }
      if (!warned[url]) {
        warned[url] = true;
        if (typeof console !== 'undefined' && console.warn) {
          console.warn('[egress-guard] 已拦截 ' + (kind || '请求') + ': ' + url);
        }
      }
      if (pending[url] === undefined) {
        if (pendingCount >= MAX_PENDING) { return; }
        pendingCount += 1;
        pending[url] = 0;
      }
      pending[url] += 1;
      scheduleFlush();
    } catch (error) { /* 拦截上报绝不破坏页面 */ }
  }

  function csrfToken() {
    try {
      var match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
      return match ? decodeURIComponent(match[1]) : '';
    } catch (error) {
      return '';
    }
  }

  function flushNow() {
    var events = [];
    for (var url in pending) {
      if (Object.prototype.hasOwnProperty.call(pending, url)) {
        events.push({ url: url, count: pending[url] });
      }
    }
    pending = {};
    pendingCount = 0;
    if (!events.length || !nativeFetch) { return; }
    try {
      nativeFetch(REPORT_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify({ events: events }),
        keepalive: true,
        credentials: 'same-origin',
      }).catch(function () { });
    } catch (error) { }
  }

  function scheduleFlush() {
    if (flushTimer !== null) { return; }
    flushTimer = setTimeout(function () {
      flushTimer = null;
      flushNow();
    }, FLUSH_MS);
  }

  var nativeFetch = window.fetch ? window.fetch.bind(window) : null;
  if (nativeFetch) {
    window.fetch = function (input, init) {
      var url = input && typeof input !== 'string' ? input.url : input;
      if (!isAllowedUrl(url)) {
        report(url, 'fetch');
        return Promise.reject(new TypeError('Failed to fetch'));
      }
      return nativeFetch(input, init);
    };
  }

  var nativeXhrOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    if (!isAllowedUrl(url)) {
      report(url, 'XHR');
      throw new Error('请求已被拦截: ' + url);
    }
    return nativeXhrOpen.apply(this, arguments);
  };

  var NativeWebSocket = window.WebSocket;
  if (NativeWebSocket) {
    function GuardedWebSocket(url, protocols) {
      if (!isAllowedUrl(url)) {
        report(url, 'WebSocket');
        throw new Error('请求已被拦截: ' + url);
      }
      return arguments.length > 1 ? new NativeWebSocket(url, protocols) : new NativeWebSocket(url);
    }
    GuardedWebSocket.prototype = NativeWebSocket.prototype;
    GuardedWebSocket.CONNECTING = NativeWebSocket.CONNECTING;
    GuardedWebSocket.OPEN = NativeWebSocket.OPEN;
    GuardedWebSocket.CLOSING = NativeWebSocket.CLOSING;
    GuardedWebSocket.CLOSED = NativeWebSocket.CLOSED;
    window.WebSocket = GuardedWebSocket;
  }

  var NativeEventSource = window.EventSource;
  if (NativeEventSource) {
    function GuardedEventSource(url, config) {
      if (!isAllowedUrl(url)) {
        report(url, 'EventSource');
        throw new Error('请求已被拦截: ' + url);
      }
      return config === undefined ? new NativeEventSource(url) : new NativeEventSource(url, config);
    }
    GuardedEventSource.prototype = NativeEventSource.prototype;
    window.EventSource = GuardedEventSource;
  }

  if (navigator.sendBeacon) {
    var nativeBeacon = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = function (url, data) {
      if (!isAllowedUrl(url)) {
        report(url, 'sendBeacon');
        return false;
      }
      return nativeBeacon(url, data);
    };
  }

  if (navigator.serviceWorker && navigator.serviceWorker.register) {
    var nativeRegister = navigator.serviceWorker.register.bind(navigator.serviceWorker);
    navigator.serviceWorker.register = function (url, options) {
      if (!isAllowedUrl(url)) {
        report(url, 'ServiceWorker');
        return Promise.reject(new TypeError('请求已被拦截'));
      }
      return nativeRegister(url, options);
    };
  }

  var nativeOpen = window.open;
  window.open = function (url) {
    if (arguments.length > 0 && !isAllowedUrl(url)) {
      report(url, 'window.open');
      return null;
    }
    return nativeOpen.apply(this, arguments);
  };

  function hookLoadProperty(ctorName, prop) {
    try {
      var proto = window[ctorName] && window[ctorName].prototype;
      if (!proto) { return; }
      var desc = Object.getOwnPropertyDescriptor(proto, prop);
      if (!desc || !desc.get || !desc.set) { return; }
      Object.defineProperty(proto, prop, {
        get: function () { return desc.get.call(this); },
        set: function (value) {
          if (isAllowedUrl(value)) {
            desc.set.call(this, value);
          } else {
            report(value, ctorName + '.' + prop);
          }
        },
        configurable: true,
        enumerable: desc.enumerable,
      });
    } catch (error) { }
  }

  hookLoadProperty('HTMLScriptElement', 'src');
  hookLoadProperty('HTMLImageElement', 'src');
  hookLoadProperty('HTMLImageElement', 'srcset');
  hookLoadProperty('HTMLLinkElement', 'href');
  hookLoadProperty('HTMLIFrameElement', 'src');
  hookLoadProperty('HTMLMediaElement', 'src');
  hookLoadProperty('HTMLSourceElement', 'src');
  hookLoadProperty('HTMLSourceElement', 'srcset');
  hookLoadProperty('HTMLTrackElement', 'src');
  hookLoadProperty('HTMLObjectElement', 'data');
  hookLoadProperty('HTMLEmbedElement', 'src');
  hookLoadProperty('HTMLVideoElement', 'poster');
  hookLoadProperty('HTMLFormElement', 'action');
  hookLoadProperty('HTMLInputElement', 'formAction');
  hookLoadProperty('HTMLButtonElement', 'formAction');

  var BLOCKED_ATTRS = ['src', 'srcset', 'data', 'poster', 'action', 'formaction'];

  var nativeSetAttribute = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (name, value) {
    var key = String(name || '').toLowerCase();
    if (BLOCKED_ATTRS.indexOf(key) !== -1 && !isAllowedUrl(value)) {
      report(value, '@' + key);
      return;
    }
    return nativeSetAttribute.call(this, name, value);
  };

  function sanitizeElement(el) {
    try {
      for (var i = 0; i < BLOCKED_ATTRS.length; i++) {
        var name = BLOCKED_ATTRS[i];
        var value = el.getAttribute(name);
        if (value != null && !isAllowedUrl(value)) {
          el.removeAttribute(name);
          report(value, 'DOM @' + name);
        }
      }
    } catch (error) { }
  }

  function sanitizeTree(root) {
    try {
      sanitizeElement(root);
      if (root.querySelectorAll) {
        var nodes = root.querySelectorAll('[src],[srcset],[data],[poster],[action],[formaction]');
        for (var i = 0; i < nodes.length; i++) { sanitizeElement(nodes[i]); }
      }
    } catch (error) { }
  }

  if (window.MutationObserver) {
    new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        var added = mutations[i].addedNodes;
        for (var j = 0; j < added.length; j++) {
          if (added[j].nodeType === 1) { sanitizeTree(added[j]); }
        }
      }
    }).observe(document.documentElement || document, { childList: true, subtree: true });
  }

  try {
    var meta = document.createElement('meta');
    meta.setAttribute('name', 'referrer');
    meta.setAttribute('content', 'no-referrer');
    var head = document.head || document.documentElement;
    head.insertBefore(meta, head.firstChild);
  } catch (error) { }

  try {
    window.addEventListener('pagehide', flushNow);
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') { flushNow(); }
    });
  } catch (error) { }
})();
