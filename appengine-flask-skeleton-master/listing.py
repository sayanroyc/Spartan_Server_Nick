from flask import Flask,request,json,jsonify,Response,abort
import datetime, time
import global_vars
from google.appengine.ext import ndb
from google.appengine.api import search
from gcloud import storage
from models import User,Category,Listing
from error_handlers import InvalidUsage

app = Flask(__name__)


# Create a new listing object and put into Datastore and Search App
@app.route('/listing/create/user_id=<int:user_id>', methods=['POST'])
def create_new_listing(user_id):
	json_data 			= request.get_json()
	name 				= json_data.get('name','')
	item_description 	= json_data.get('item_description','')
	total_value			= float(json_data.get('total_value',''))
	hourly_rate 		= float(json_data.get('hourly_rate',''))
	daily_rate			= float(json_data.get('daily_rate',''))
	weekly_rate 		= float(json_data.get('weekly_rate',''))
	category_id 		= int(json_data.get('category_id',''))
	# location_lat 		= float(json_data.get('location_lat',''))
	# location_lon		= float(json_data.get('location_lon',''))


	# Check to see if the user exists
	u = User.get_by_id(user_id)
	if u is None:
		raise InvalidUsage('UserID does not match any existing user', status_code=400)

	u_key = ndb.Key('User', user_id)
	c_key = ndb.Key('Category', category_id)

	# if total_value > MAX_ITEM_VALUE:
	# 	raise InvalidUsage('Total value is too large', status_code=400)

	status = 'Available'
	rating = -1.0

	# Add listing to Datastore
	l = Listing(owner=u_key, status=status, name=name, item_description=item_description, 
				rating=rating, total_value=total_value, hourly_rate=hourly_rate, daily_rate=daily_rate, 
				weekly_rate=weekly_rate, category=c_key, location=u.last_known_location)
	try:
		listing_key = l.put()
		listing_id	= str(listing_key.id())
	except:
		abort(500)

	# Add listing to Search App
	new_item = search.Document(
		doc_id=listing_id,
		fields=[search.TextField(name='name', value=name),
				search.GeoField(name='location', value=search.GeoPoint(u.last_known_location.lat,u.last_known_location.lon)),
				search.TextField(name='owner_id', value=str(user_id))])
	try:
		index = search.Index(name='Listing')
		index.put(new_item)
	except:
		abort(500)

	
	data = {'listing_id':listing_id, 'date_created':l.date_created, 'date_last_modified':l.date_last_modified, 'status':status}
	resp = jsonify(data)
	resp.status_code = 201
	return resp



# Delete listing from Search API and set status to 'Deleted' in Datastore
@app.route('/listing/delete/listing_id=<int:listing_id>', methods=['DELETE'])
def delete_listing(listing_id):
	# Delete Search App entity
	try:
		index = search.Index(name='Listing')
		index.delete(str(listing_id))
	except:
		abort(500)


	# Edit Datastore entity
	# Get the listing
	l = Listing.get_by_id(listing_id)
	if l is None:
		raise InvalidUsage('Listing ID does not match any existing listing.', 400)

	# Set listing status to 'Deleted'
	l.status = 'Deleted'

	# Add the updated listing status to the Datastore
	try:
		l.put()
	except:
		abort(500)


	# Return response
	data = {'listing_id deleted':listing_id, 'date_deleted':l.date_last_modified}
	resp = jsonify(data)
	resp.status_code = 200
	return resp




# Add a listing image
MAX_NUM_ITEM_IMAGES = 5
@app.route('/listing/new_listing_image/listing_id=<int:listing_id>', methods=['POST'])
def new_listing_image(listing_id):
	# user_id = request.form['user_id']
	# listing_id = request.form['listing_id']
	userfile = request.files['userfile']
	filename = userfile.filename

	# Check if listing exists
	l = Listing.get_by_id(listing_id)
	if l is None:
		raise InvalidUsage('Listing does not exist!', status_code=400)

	# Create client for interfacing with Cloud Storage API
	client = storage.Client()
	bucket = client.get_bucket(global_vars.LISTING_IMG_BUCKET)

	# Returns an iterator through all images for the item
	# listing_img_objects = bucket.list_blobs(prefix=str(listing_id))

	# Count how many images we have (is there a better way to do this?)
	# curr_item_images = 0
	# for img in listing_img_objects:
	# 	curr_item_images += 1

	# if curr_item_images >= MAX_NUM_ITEM_IMAGES:
	# 	raise InvalidUsage('Too many pictures!', status_code=400)

	# Calculating size this way is not very efficient. Is there another way?
	userfile.seek(0, 2)
	size = userfile.tell()
	userfile.seek(0)

	# upload the item image
	path = str(listing_id)+'/'+filename
	image = bucket.blob(blob_name=path)
	image.upload_from_file(file_obj=userfile, size=size, content_type='image/jpeg')
	
	# Hacky way of making the image public..
	image.acl.all().grant_read()
	image.acl.save()

	resp = jsonify({'image_path':path, 'image_media_link':image.media_link})
	resp.status_code = 201
	return resp




# Delete a listing image
@app.route('/listing/delete_listing_image/path=<path:path>', methods=['DELETE'])
def delete_listing_image(path):
	# Create client for interfacing with Cloud Storage API
	client = storage.Client()
	bucket = client.get_bucket(global_vars.LISTING_IMG_BUCKET)
	
	# Delete the image from the given path
	bucket.delete_blob(path)

	now = datetime.datetime.now()
	now_str = now.strftime("%Y %m %d %H:%M:%S")

	# Return response
	resp = jsonify({'picture_id deleted':path, 'date_deleted':now_str})
	resp.status_code = 200
	return resp





# Returns a string of the current datetime
def get_current_datetime():
	now = datetime.datetime.now()
	return now.strftime("%Y %m %d %H:%M:%S")


### Server Error Handlers ###
@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
	response = jsonify(error.to_dict())
	response.status_code = error.status_code
	return response

@app.errorhandler(404)
def page_not_found(e):
	"""Return a custom 404 error."""
	return 'Sorry, Nothing at this URL.', 404

@app.errorhandler(500)
def application_error(e):
	"""Return a custom 500 error."""
	return 'Sorry, unexpected error: {}'.format(e), 500