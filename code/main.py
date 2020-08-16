from google.cloud import datastore
from flask import Flask, request, render_template
from requests_oauthlib import OAuth2Session
import json
import constants
import requests
from google.oauth2 import id_token
from google.auth.transport import requests
from datetime import datetime

app = Flask(__name__)
client = datastore.Client()
Error = dict()


# These should be copied from an OAuth2 Credential section at
# https://console.cloud.google.com/apis/credentials
client_id = 'secret'
client_secret = 'secret'

# This is the page that you will use to decode and collect the info from
# the Google authentication flow
redirect_uri = 'https://sunderla-final-1.wl.r.appspot.com/oauth'

# These let us get basic info to identify a user and not much else
# they are part of the Google People API
scope = ['https://www.googleapis.com/auth/userinfo.email',
             'https://www.googleapis.com/auth/userinfo.profile', 'openid']
oauth = OAuth2Session(client_id, redirect_uri=redirect_uri,
                          scope=scope)

# This link will redirect users to begin the OAuth flow with Google
@app.route('/')
def index():
    authorization_url, state = oauth.authorization_url(
        'https://accounts.google.com/o/oauth2/auth',
        # access_type and prompt are Google specific extra
        # parameters.
        access_type="offline", prompt="select_account")
    return 'Please go <a href=%s>here</a> and authorize access.' % authorization_url

# This is where users will be redirected back to and where you can collect
# the JWT for use in future requests
@app.route('/oauth')
def oauthroute():
    token = oauth.fetch_token(
        'https://accounts.google.com/o/oauth2/token',
        authorization_response=request.url,
        client_secret=client_secret)
    req = requests.Request()
    id_info = id_token.verify_oauth2_token(token['id_token'], req, client_id)
    query = client.query(kind=constants.users)
    new_user = datastore.entity.Entity(key=client.key(constants.users))
    results = list(query.fetch())
    for item in results:
        if item['sub'] == id_info['sub']:
            user_key = client.key(constants.users, int(item['id']))
            user = client.get(key=user_key)
            user["jwt"] = token['id_token']
            client.put(user)
            return render_template('index.html', jwt=token['id_token'], sub=id_info['sub'])

    new_user.update({"jwt": token['id_token'], "sub": id_info['sub'], "email": id_info['email'], "boat": None})
    client.put(new_user)
    new_user["id"] = new_user.key.id
    client.put(new_user)
    return render_template('index.html', jwt=token['id_token'], sub=id_info['sub'])


@app.route('/users', methods=['GET'])
def users_get():
    if request.method == 'GET':
        query = client.query(kind=constants.users)
        results = list(query.fetch())
        if 'application/json' in request.accept_mimetypes:
            return json.dumps(results)
        else:
            Error["Error"] = "Content type not supported by endpoint"
            return Error, 406

    else:
        return 'Method not recognized'


@app.route('/boats', methods=['POST','GET'])
def boats_get_post():
    if request.method == 'POST':
        content = request.get_json()
        req = requests.Request()
        try:
            token = request.headers.get('Authorization')[7:]
            id_info = id_token.verify_oauth2_token(token, req, client_id)
        except:
            Error["Error"] = "Missing or invalid JWT"
            return Error, 401
        if len(content) < 3:
            Error["Error"] = "The request object is missing at least one of the required attributes"
            return Error, 400
        new_boat = datastore.entity.Entity(key=client.key(constants.boats))
        new_boat.update({"name": content["name"], "type": content["type"], "length": content["length"], "owner": id_info["sub"], "slip": None})
        client.put(new_boat)
        new_boat["id"] = new_boat.key.id
        new_boat["self"] = str(request.url) + '/' + str(new_boat["id"])
        client.put(new_boat)
        if 'application/json' in request.accept_mimetypes:
            return new_boat, 201
        else:
            Error["Error"] = "Content type not supported by endpoint"
            return Error, 406

    elif request.method == 'GET':
        req = requests.Request()
        try:
            token = request.headers.get('Authorization')[7:]
            id_info = id_token.verify_oauth2_token(token, req, client_id)
        except:
            Error["Error"] = "Missing or invalid JWT"
            return Error, 401

        query = client.query(kind=constants.boats)
        query.add_filter('owner', '=', id_info["sub"])
        q_limit = int(request.args.get('limit', '5'))
        q_offset = int(request.args.get('offset', '0'))
        l_iterator = query.fetch(limit=q_limit, offset=q_offset)
        pages = l_iterator.pages
        results = list(next(pages))
        if l_iterator.next_page_token:
            next_offset = q_offset + q_limit
            next_url = request.base_url + "?limit=" + str(q_limit) + "&offset=" + str(next_offset)
        else:
            next_url = None
        output = {"boats": results}
        if next_url:
            output["next"] = next_url
        if 'application/json' in request.accept_mimetypes:
            return json.dumps(output)
        else:
            Error["Error"] = "Content type not supported by endpoint"
            return Error, 406
    else:
        return 'Method not recogonized'


@app.route('/boats/<id>', methods=['PUT','DELETE','GET','PATCH'])
def boats_id_put_delete_get_patch(id):
    req = requests.Request()
    try:
        token = request.headers.get('Authorization')[7:]
        id_info = id_token.verify_oauth2_token(token, req, client_id)
    except:
        Error["Error"] = "Missing or invalid JWT"
        return Error, 401
    boat_key = client.key(constants.boats, int(id))
    boat = client.get(key=boat_key)
    if boat["owner"] != id_info["sub"]:
        Error["Error"] = "This user doesn't have permission."
        return Error, 403
    if request.method == 'PATCH':
        content = request.get_json()
        if len(content) < 1:
            Error["Error"] = "The request object is missing at least one of the required attributes"
            return Error, 400
        if boat is None:
            Error["Error"] = "No boat with this boat_id exists"
            return Error, 404
        if "name" in content:
            boat.update({"name": content["name"]})
        if "type" in content:
            boat.update({"type": content["type"]})
        if "length" in content:
            boat.update({"length": content["length"]})

        client.put(boat)
        boat["id"] = boat.key.id
        boat["self"] = str(request.url)
        if 'application/json' in request.accept_mimetypes:
            return boat, 200
        else:
            Error["Error"] = "Content type not supported by endpoint"
            return Error, 406
    elif request.method == 'PUT':
        content = request.get_json()
        boat.update({"name": content["name"], "type": content["type"],
          "length": content["length"]})
        client.put(boat)
        if 'application/json' in request.accept_mimetypes:
            return boat, 200
        else:
            Error["Error"] = "Content type not supported by endpoint"
            return Error, 406
    elif request.method == 'DELETE':
        if boat is None:
            Error["Error"] = "No boat with this boat_id exists"
            return Error, 404
        client.delete(boat_key)
        query = client.query(kind=constants.slips)
        results = list(query.fetch())
        for e in results:
            if e["current_boat"] == boat.key.id:
                e.update({"current_boat": None})
                client.put(e)
        return ('',204)
    elif request.method == 'GET':
        if boat is None:
            Error["Error"] = "No boat with this boat_id exists"
            return Error, 404
        boat["id"] = boat.key.id
        boat["self"] = str(request.url)
        if 'application/json' in request.accept_mimetypes:
            return boat, 200
        else:
            Error["Error"] = "Content type not supported by endpoint"
            return Error, 406
    else:
        return 'Method not recogonized'


@app.route('/slips', methods=['POST','GET'])
def slips_get_post():
    if request.method == 'POST':
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        content = request.get_json()
        if "number" not in content:
            Error["Error"] = "The request object is missing the required number"
            return Error, 400
        new_slip = datastore.entity.Entity(key=client.key(constants.slips))
        new_slip.update({"number": content["number"], "current_boat": None, "date-created": current_time, "last-modified": current_time})
        client.put(new_slip)
        new_slip["id"] = new_slip.key.id
        new_slip["self"] = str(request.url) + '/' + str(new_slip["id"])
        client.put(new_slip)
        if 'application/json' in request.accept_mimetypes:
            return new_slip, 201
        else:
            Error["Error"] = "Content type not supported by endpoint"
            return Error, 406
    elif request.method == 'GET':
        query = client.query(kind=constants.slips)
        q_limit = int(request.args.get('limit', '5'))
        q_offset = int(request.args.get('offset', '0'))
        l_iterator = query.fetch(limit=q_limit, offset=q_offset)
        pages = l_iterator.pages
        results = list(next(pages))
        if l_iterator.next_page_token:
            next_offset = q_offset + q_limit
            next_url = request.base_url + "?limit=" + str(q_limit) + "&offset=" + str(next_offset)
        else:
            next_url = None
        output = {"slips": results}
        if next_url:
            output["next"] = next_url
        if 'application/json' in request.accept_mimetypes:
            return json.dumps(output)
        else:
            Error["Error"] = "Content type not supported by endpoint"
            return Error, 406
    else:
        return 'Method not recogonized'


@app.route('/slips/<id>', methods=['DELETE','GET','PUT','PATCH'])
def slips_id_delete_get_put_patch(id):
    slip_key = client.key(constants.slips, int(id))
    slip = client.get(key=slip_key)
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    if request.method == 'DELETE':
        if slip is None:
            Error["Error"] = "No slip with this slip_id exists"
            return Error, 404
        if slip["current_boat"] is not None:
            boat_key = client.key(constants.boats, int(slip["current_boat"]))
            boat = client.get(key=boat_key)
            boat.update({"slip": None})
            client.put(boat)
        client.delete(slip_key)
        return ('',204)
    elif request.method == 'GET':
        if slip is None:
            Error["Error"] = "No slip with this slip_id exists"
            return Error, 404
        slip["id"] = slip.key.id
        slip["self"] = str(request.url)
        if 'application/json' in request.accept_mimetypes:
            return slip, 200
        else:
            Error["Error"] = "Content type not supported by endpoint"
            return Error, 406

    elif request.method == 'PATCH':
        content = request.get_json()
        if len(content) < 1:
            Error["Error"] = "The request object is missing at least one of the required attributes"
            return Error, 400
        if slip is None:
            Error["Error"] = "No slip with this slip_id exists"
            return Error, 404
        if "number" in content:
            slip.update({"number": content["number"], "last-modified": current_time})
        client.put(slip)
        slip["id"] = slip.key.id
        slip["self"] = str(request.url)
        if 'application/json' in request.accept_mimetypes:
            return slip, 200
        else:
            Error["Error"] = "Content type not supported by endpoint"
            return Error, 406
    elif request.method == 'PUT':
        content = request.get_json()
        if len(content) < 1:
            Error["Error"] = "The request object is missing at least one of the required attributes"
            return Error, 400
        if slip is None:
            Error["Error"] = "No slip with this slip_id exists"
            return Error, 404
        if "number" in content:
            slip.update({"number": content["number"], "last-modified": current_time})
        client.put(slip)
        slip["id"] = slip.key.id
        slip["self"] = str(request.url)
        if 'application/json' in request.accept_mimetypes:
            return slip, 200
        else:
            Error["Error"] = "Content type not supported by endpoint"
            return Error, 406
    else:
        return 'Method not recogonized'


@app.route('/slips/<slip_id>/<boat_id>', methods=['PUT', 'DELETE'])
def slips_id_put_delete(slip_id, boat_id):
    if request.method == 'DELETE':
        boat_key = client.key(constants.boats, int(boat_id))
        boat = client.get(key=boat_key)
        slip_key = client.key(constants.slips, int(slip_id))
        slip = client.get(key=slip_key)
        if boat is None or slip["current_boat"] != boat.key.id:
            Error["Error"] = "No boat with this boat_id is at the slip with this slip_id"
            return Error, 404
        slip.update({"current_boat": None})
        boat.update({"slip": None})
        client.put(boat)
        client.put(slip)
        return ('',204)

    elif request.method == 'PUT':
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        boat_key = client.key(constants.boats, int(boat_id))
        boat = client.get(key=boat_key)
        slip_key = client.key(constants.slips, int(slip_id))
        slip = client.get(key=slip_key)
        if boat is None or slip is None:
            Error["Error"] = "The specified boat and/or slip don" + u"\u2019" + "t exist"
            return Error, 404
        elif slip["current_boat"] is not None:
            Error["Error"] = "The slip is not empty"
            return Error, 403
        slip.update({"current_boat": boat.key.id, "last-modified": current_time})
        boat.update({"slip": slip.key.id})
        client.put(slip)
        client.put(boat)
        return ('',204)
    else:
        return 'Method not recogonized'


if __name__ == '__main__':
    app.run(host='localhost', port=8080, debug=True)