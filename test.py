import nextgis
import pydrive
from config import Config  # Параметры записаны в файл config.py
import datetime
import pytz

if __name__ == "__main__":
    resource = 81
    # print(nextgis.get_features_array(55, limit=5, offset=55, order_by=['name', 'wi_addr_building'],
    #                                  fields_list=['id']))
    # print(nextgis.get_features_array(51))
    # json_object = nextgis.get_features(55, fields=['id', 'name', 'google_folder_id', 'wi_addr_locality',
    #                                                'wi_addr_street', 'wi_addr_building', 'link_google_drive'],
    #                                    fld_filter=['fld_google_folder_id__ne=Null'], geom='no', extensions='none')
    json_object = nextgis.get_features(resource, geom='no', extensions='none')

    # json_object = nextgis.get_feature(55, 15, fields=['id'])
    # print(json_object['id'], json_object['fields']['id'])

    # json_object = nextgis.get_feature(55, 15, fields=['id', 'name'],
    #                                    dt_format='iso', geom_format='geojson', srs='4326', extensions='none')

    print(json_object)
    # resource_id = 55
    # print(json_object[0]['id'], json_object[0]['fields']['id'])
    for song in json_object:
        feature_id = song['id']
    #     locality = song['fields']['wi_addr_locality']
    #     street = song['fields']['wi_addr_street']
    #     building = song['fields']['wi_addr_building']
    #     landmark = song['fields']['wi_landmark']
    #     specification = song['fields']['wi_specification']
    #
    #     name_folder = f"ИД-{feature_id} {name} {locality}, {street}, {building}"
        fields = {'ИД': feature_id}
        # print(folder_id, name_folder)

        # print(PyDrive.create_folder(file_id=folder_id, file_name=name_folder, parent_folder=Config.parent_folder_id))
        # print(song['id'], song['fields']['name'])

        nextgis.ngw_put_feature(resource, feature_id, fields)
        # for attribute, value in song.items():
        #     print(attribute, value)

    # current_time = datetime.datetime.now(pytz.timezone(Config.timezone))
    # print({'year': "{:02d}".format(current_time.year),
    #        'month': "{:02d}".format(current_time.month),
    #        'day': "{:02d}".format(current_time.day),
    #        'hour': "{:02d}".format(current_time.hour),
    #        'minute': "{:02d}".format(current_time.minute)})