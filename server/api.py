import traceback

from flask import current_app, jsonify, request
from flask_mongoengine import MongoEngine
from flask_security import MongoEngineUserDatastore, Security

from helper import *

# from server import user_datastore


class Api():
    def __init__(self, db):
        """Init function for Api class.

        Keyword arguments:
        db -- The DB connection for the Flask app.

        Sets the instance variable.
        """
        self.user_datastore = MongoEngineUserDatastore(db, User, Role)

    def register(self, claims):
        """Register a new account in system

        Keyword arguments:
        claims -- The JWT claims that are being passed to this methods. Must include email and password for successful creation.

        Returns a HTTP response.
        """
        email, password = None, None
        try:
            if claims is not None:
                # Use a dict access here, not ".get". The access is better with the try block.
                email = str(claims['email'])
                password = str(claims['password'])
            else:
                return jsonify(error="Forbidden"), 403, json_tag
        except Exception as e:
            current_app.logger.error(e)
            if not current_app.testing:
                current_app.logger.error(e)
            return malformed_request()

        validation = Helper.validate_register(email, password)
        if validation[0] is True:
            return jsonify(error=validation[1]), 422, json_tag

        # Hash and create user
        self.user_datastore.create_user(
            email=email, password=Helper.hashpw(password))

        # So we can log user in automatically after registration
        token = User.objects(email=email).first().generate_auth_token()

        # TODO: error handle this and if it doesn't work do something else besides the success in jsonify
        # send_email(recipients=email, subject="ay whaddup", text="Hello from AR-top")
        return jsonify(success="Account has been created! Check your email to validate your account.", auth_token=token.decode('utf-8')), 200, json_tag

    def authenticate(claims):
        """Verify a login attempt.

        Keyword arguments:
        claims -- The JWT claims that are being passed to this methods. Must include email and password for successful login.

        Returns a HTTP response.
        """
        email, password, error = None, None, None
        try:
            # Use a dict access here, not ".get". The access is better with the try block.
            if claims is not None:
                email = claims['email']
                password = claims["password"]
            else:
                return jsonify(error="Forbidden"), 403, json_tag
        except Exception as e:
            current_app.logger.error(str(e))
            return jsonify(error="Malformed Request; expecting email and password"), 422, json_tag

        validator = Helper.validate_auth(email, password)

        if validator[0] is True:
            return jsonify(error=validator[1]), 422, json_tag
        else:
            return jsonify(email=email, auth_token=validator[2]), 200, json_tag

    def read_map(claims, id):
        """Gather all maps associated with a user.

        Keyword arguments:
        claims -- The JWT claims that are being passed to this methods. Must include email.
        id -- The ID that is associated with the requested map.

        Returns a HTTP response.
        """
        email, user, map = None, None, None
        try:
            email = claims["email"]
            user = User.objects(email=email).first()
        except Exception as e:
            return malformed_request()

        try:
            map = Map.objects.get(id=id, user=user)
        except (StopIteration, DoesNotExist) as e:
            # Malicious user may be trying to overwrite someone's map
            # or there actually is something wrong; treat these situations the same
            return jsonify(error="Map does not exist"), 404, json_tag
        except:
            return internal_error()

        return map.to_json(), 200, json_tag

    def read_list_of_maps(claims, user_id):
        """Gather all maps associated with a user.

        Keyword arguments:
        claims -- The JWT claims that are being passed to this methods. Must include email.
        id -- The ID that is associated with the requested map.

        Returns a HTTP response.
        """
        token = claims['auth_token']
        token_user = User.verify_auth_token(token)
        map_list = None
        if token_user is None:
            error = "token expired"
        # I am assuming that the user will need to login again and I don't need to check password here
        else:
            map_list = Map.objects(user=token_user)
            if map_list == None:
                error = "map error"
            else:
                return map_list.to_json(), 200, json_tag
        return jsonify(error=error), 422, json_tag

    def create_map(claims):
        """Create a map for the user.

        Keyword arguments:
        claims -- The JWT claims that are being passed to this methods. Must include email.

        Returns a HTTP response.
        """
        email, map, user = None, None, None
        try:
            # Use a dict access here, not ".get". The access is better with the try block.
            email = claims["email"]
            user = User.objects(email=email).first()
            map = request.json['map']
        except Exception as e:
            if not current_app.testing:
                current_app.logger.error(str(e))
            return malformed_request()

        try:
            name = map["name"]
            width = map["width"]
            height = map["height"]
            depth = map["depth"]
            color = map["color"]
            private = map["private"]
            models = map['models']
        except Exception as e:
            current_app.logger.error(str(e))
            return malformed_request()

        try:
            new_map = Map(name=name, user=user, width=width, height=height, depth=depth,
                          color=color, private=private, models=models)
            new_map.save()
        except Exception as e:
            current_app.logger.error("Failed to save map for user",
                                     str(user), "\n", str(e))
            return internal_error()

        return jsonify(success="Successfully created map", map=new_map), 200, json_tag

    def update_map(claims, map_id):
        """Update a maps name or base color.

        Keyword arguments:
        claims -- The JWT claims that are being passed to this methods. Must include email.
        map_id -- The ID that is associated with the requested map.

        Returns a HTTP response.
        """
        try:
            # Use a dict access here, not ".get". The access is better with the try block.
            email = claims["email"]
            map = request.json['map']
            user = User.objects(email=email).first()
        except Exception as e:
            current_app.logger.error(str(e))
            return malformed_request()

        # Make sure this user is actually the author of the map
        # and that the ID also is an existing map
        remote_copy = None
        try:
            remote_copy = Map.objects.get(id=map_id, user=user)
        except (StopIteration, DoesNotExist) as e:
            # Malicious user may be trying to overwrite someone's map
            # or there actually is something wrong; treat these situations the same
            return jsonify(error="Map does not exist"), 404, json_tag
        except Exception as e:
            current_app.logger.error(str(e))
            return internal_error()

        try:
            for i in ["name", "width", "height", "depth", "color", "private", 'models']:
                attr = map.get(i)
                if attr:
                    remote_copy[i] = attr
        except Exception as e:
            current_app.logger.error(str(e))
            return internal_error()

        remote_copy.save()
        return jsonify(success="Map updated successfully", map=remote_copy), 200, json_tag

    def delete_map(claims, map_id):
        """Delete map from database.

        Keyword arguments:
        claims -- The JWT claims that are being passed to this methods. Must include email.
        map_id -- The ID that is associated with the requested map.

        Returns a HTTP response.
        """
        email = None
        try:
            email = claims["email"]
        except:
            return malformed_request()

        try:
            user = User.objects(email=email).first()
        except:
            return internal_error()

        try:
            remote_copy = Map.objects.get(id=map_id, user=user)
            remote_copy.delete()
        except (StopIteration, DoesNotExist) as e:
            # Malicious user may be trying to overwrite someone's map
            # or there actually is something wrong; treat these situations the same
            return jsonify(error="Map does not exist"), 404, json_tag
        except:
            return internal_error()

        return jsonify(success=map_id), 200, json_tag