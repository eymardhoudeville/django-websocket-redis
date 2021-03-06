.. running

===========================
Running WebSocket for Redis
===========================

**WebSocket for Redis** is a library which runs side by side with Django. It has its own separate
main loop, which does nothing else than keeping the WebSocket alive and dispatching requests
from **Redis** to the configured WebSockets and vice versa.

Django with WebSockets for Redis in development mode
====================================================
With **WebSockets for Redis**, a Django application has immediate access to code written for
WebSockets. Make sure, that Redis is up and accepts connections.

.. code-block:: bash

	$ redis-cli ping
	PONG

Then start the Django development server.

.. code-block:: bash

	./manage.py runserver

As usual, this command shall only be used for development.

The ``runserver`` command is a monkey patched version of the original Django main loop and works
similar to it. If an incoming request is of type WSGI, everything works as usual. However, if the
patched handler detects an incoming request wishing to open a WebSocket, then the Django main
loop is hijacked by **ws4redis**. This separate loop then waits until ``select`` notifies that some
data is available for further processing, or by the WebSocket itself, or by the Redis message queue.
This hijacked main loop finishes when the WebSocket is closed or when an error occurs.

.. note:: In development, one thread is created for each open WebSocket.

Opened WebSocket connections exchange so called Ping/Pong messages. They keep the connections open,
even if there is no payload to be sent. In development mode, the “WebSocket” main loop does not send
these stay alive packages, because normally there is no proxy or firewall between the server and the
client which could drop the connection. This could be easily implemented, though.

Django with WebSockets for Redis as a stand alone uWSGI server
==============================================================
In this configuration the **uWSGI** server owns the main loop. To distinguish WebSockets from
normals requests, modify the Python starter module ``wsgi.py`` to

.. code-block:: python

	import os
	os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myapp.settings')
	from django.conf import settings
	from django.core.wsgi import get_wsgi_application
	from ws4redis.uwsgi_runserver import uWSGIWebsocketServer
	
	_django_app = get_wsgi_application()
	_websocket_app = uWSGIWebsocketServer()
	
	def application(environ, start_response):
	    if environ.get('PATH_INFO').startswith(settings.WEBSOCKET_URL):
	        return _websocket_app(environ, start_response)
	    return _django_app(environ, start_response)

Run uWSGI as stand alone server with

.. code-block:: bash

	uwsgi --virtualenv /path/to/virtualenv --http :80 --gevent 100 --http-websockets --module wsgi

This will answer, both Django and WebSocket requests on port 80 using HTTP. Here the modified
``application`` dispatches incoming requests depending on the URL on either a Django handler or
into the WebSocket's main loop.

This configuration works for testing uWSGI and low traffic sites. Since uWSGI then runs in one
thread/process, blocking calls such as accessing the database, would also block all other HTTP
requests. Adding ``--gevent-monkey-patch`` to the command line may help here, but Postgres for
instance requires to monkey patch its blocking calls with **gevent** using the psycogreen_ library.
Moreover, only one CPU core is then used, and static files must be handled by another webserver.

Django with WebSockets for Redis behind NGiNX using uWSGI
=========================================================
This is the most scalable solution. Here two instances of a uWSGI server are spawned, one to handle
normal HTTP requests for Django and one to handle WebSocket requests.

|websocket4redis|

Assure that you use NGiNX version 1.3.13 or later, since earlier versions have no support for
WebSocket proxying. The web server undertakes the task of dispatching normal requests to one uWSGI
instance and WebSocket requests to another one. The responsible configuration section for
NGiNX shall look like:

.. code-block:: nginx

	location / {
	    include /etc/nginx/uwsgi_params;
	    uwsgi_pass unix:/path/to/django.socket;
	}
	
	location /ws/ {
	    proxy_http_version 1.1;
	    proxy_set_header Upgrade $http_upgrade;
	    proxy_set_header Connection "upgrade";
	    proxy_pass http://unix:/path/to/web.socket;
	}

For details refer to NGiNX's configuration on `WebSocket proxying`_.

.. _WebSocket proxying: http://nginx.org/en/docs/http/websocket.html

Since both uWSGI handlers create their own main loop, they also require their own application and
different UNIX sockets. Create two adopter files, one for the Django loop, say ``wsgi_django.py``

.. code-block:: python

	import os
	os.environ.update(DJANGO_SETTINGS_MODULE='my_app.settings')
	from django.core.wsgi import get_wsgi_application
	application = get_wsgi_application()

and one for the WebSocket loop, say ``wsgi_websocket.py``

.. code-block:: python

	import os
	import gevent.socket
	import redis.connection
	redis.connection.socket = gevent.socket
	os.environ.update(DJANGO_SETTINGS_MODULE='my_app.settings')
	from ws4redis.uwsgi_runserver import uWSGIWebsocketServer
	application = uWSGIWebsocketServer()

Start those two applications as separate uWSGI instances

.. code-block:: bash

	uwsgi --virtualenv /path/to/virtualenv --socket /path/to/django.socket --buffer-size=32768 --workers=5 --master --module wsgi_django
	uwsgi --virtualenv /path/to/virtualenv --http-socket /path/to/web.socket --gevent 1000 --http-websockets --workers=2 --master --module wsgi_websocket

The NGiNX web server is now configured as a scalable application server which can handle a thousand
WebSockets connections concurrently.

If you feel uncomfortable with separating WebSocket from normal requests on NGiNX, consider
that you already separate static and media requests on the web server. Hence, WebSockets are just
another extra routing path.

.. |websocket4redis| image:: _static/websocket4redis.png
.. _psycogreen: https://bitbucket.org/dvarrazzo/psycogreen/
