#-*- coding: utf-8 -*-

"""
 (c) 2015 - Copyright Red Hat Inc

 Authors:
   Pierre-Yves Chibon <pingou@pingoured.fr>

API namespace version 0.

"""

import flask

API = flask.Blueprint('api_ns', __name__, url_prefix='/api/0')


from progit import __api_version__, APP, SESSION
import progit
import progit.lib


@API.route('/version/')
@API.route('/version')
def api_version():
    '''
    API Version
    -----------
    Display the most recent api version.

    ::

        /api/version

    Accepts GET queries only.

    Sample response:

    ::

        {
          "version": "1"
        }

    '''
    return flask.jsonify({'version': __api_version__})


@API.route('/users/')
@API.route('/users')
def api_users():
    '''
    List users
    -----------
    Returns the list of all users that have logged into this progit instances.
    This can then be used as input for autocompletion in some forms/fields.

    ::

        /api/users

    Accepts GET queries only.

    Sample response:

    ::

        {
          "users": ["user1", "user2"]
        }

    '''
    pattern = flask.request.args.get('pattern', None)
    if pattern is not None and not pattern.endswith('*'):
        pattern += '*'

    print pattern

    return flask.jsonify(
        {
            'users': [
                user.username
                for user in progit.lib.get_all_users(
                    SESSION, pattern=pattern)
            ]
        }
    )