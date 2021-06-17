import json
import sys
import datetime
import random
import logging
import re
import uuid
import time
import inspect
import boto3
import os
from botocore.exceptions import ClientError

# Setting Global Variables
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.DEBUG)


def lineno():  # pragma: no cover
    """
    Returns the current line number in our script
    :return:
    """
    return str(' - line number: ' + str(inspect.currentframe().f_back.f_lineno))

# DynamoDB functions

def get_dynamodb_client():
    """
    Get dynamodb client
    :return:
    """
    try:
        return boto3.client('dynamodb')
    except ClientError as err:
        print("Unexpected error: %s" % err)


def list_tables(client):
    """
    List the dynamodb tables
    :param client:
    :return:
    """
    try:
        return client.list_tables()
    except ClientError as err:
        print("Unexpected error:" + str(err) + lineno())


def query_hostname_in_dynamodb_table(client, table, hostname):
    """
    Query item in dynamodb table
    :param client:
    :param table:
    :param hostname:
    :return:
    """
    try:
        return client.query(
            TableName=str(table),
            ExpressionAttributeValues={
                ':hostname': {'S': hostname}
            },
            KeyConditionExpression='hostname = :hostname'
        )
    except ClientError as err:
        print("Unexpected error:" + str(err) + lineno())

def put_item_in_dynamodb_table(client, table, hostname, ipaddress, instance_id):
    """
    Put item in dynamodb table
    :param client:
    :param table:
    :param hostname:
    :param ipaddress:
    :param instance_id
    :return:
    """
    try:
        LOGGER.debug("Instance ID: %s", str(instance_id) + lineno())
        LOGGER.debug("IP address: %s", str(ipaddress) + lineno())
        LOGGER.debug("Putting IP address to DB: %s", str(ipaddress) + lineno())

        return client.update_item(
            TableName=str(table),
            ExpressionAttributeNames={
                '#ip': 'ipaddress',
                '#iid': 'instance_id'
            },
            ExpressionAttributeValues={
                ':ip': {'S': str(ipaddress)},
                ':iid': {'S': str(instance_id)}
            },
            Key={
                'hostname': {'S': str(hostname)},
            },
            UpdateExpression='SET #ip = :ip, #iid = :iid'
        )
    except ClientError as err:
        print("Unexpected error:" + str(err) + lineno())

def delete_item_in_dynamodb_table(client, table, hostname):
    """
    Remove item in dynamodb table
    :param client:
    :param table:
    :param hostname
    :return:
    """
    try:
        return client.delete_item(
            TableName=str(table),
            Key={
                'hostname': {'S': str(hostname)},
            }
        )
    except ClientError as err:
        print("Unexpected error:" + str(err) + lineno())

# EC2 functions
def get_ec2_client():
    """
    Get ec2 client
    :return:
    """
    try:
        return boto3.client('ec2')
    except ClientError as err:
        print("Unexpected error: %s" % err)


def get_instance_info(client, instance_id):
    """
    Get ec2 instance information
    :param instance_id
    :return:
    """
    try:
        return client.describe_instances(InstanceIds=[instance_id])
    except ClientError as err:
        print("Unexpected error:" + str(err) + lineno())

# Route53 function
def get_route53_client():
    """
    Get route53 client
    :return:
    """
    try:
        return boto3.client('route53')
    except ClientError as err:
        print("Unexpected error: %s" % err)

def change_resource_recordset(client, zone_id, host_name, hosted_zone_name, record_type, value, action):
    """
    Change resource recordset
    :param client:
    :param zone_id:
    :param host_name:
    :param hosted_zone_name:
    :param record_type
    :param value:
    :param action:
    :return:
    """
    try:
        response = client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                "Comment": "Updated by Lambda DDNS",
                "Changes": [
                    {
                        "Action": action,
                        "ResourceRecordSet": {
                            "Name": host_name + '.' + hosted_zone_name,
                            "Type": record_type,
                            "TTL": 60,
                            "ResourceRecords": [
                                {
                                    "Value": value
                                },
                            ]
                        }
                    },
                ]
            }
        )

        LOGGER.debug("response: %s", str(response) + lineno())
        return response
    except ClientError as err:
        LOGGER.debug("Error creating resource record: %s", str(err) + lineno())
        error_message = str(err)

        if "conflicts with other records" in error_message:
            LOGGER.debug(
                "Can not create dns record because of duplicates: %s", str(err) + lineno())
            return 'Duplicate resource record'
        elif "conflicting RRSet" in error_message:
            LOGGER.debug(
                "Can not create dns record because of duplicates: %s", str(err) + lineno())
            return 'Conflicting resource record'
        else:
            return 'Unexpected error: ' + str(err)

# Main Lambda function


def lambda_handler(
        event,
        context,
):
    """
    Check to see whether a DynamoDB table already exists.  If not, create it.
    This table is used to keep a record of instances that have been created
    along with their attributes.  This is necessary because when you terminate an instance
    its attributes are no longer available, so they have to be fetched from the table.
    :param event:
    :param context:
    :param dynamodb_client:
    :param compute:
    :param route53:
    :return:
    """
    # Debug
    LOGGER.info("event: %s", str(event) + lineno())
    LOGGER.info("context: %s", str(context) + lineno())
    print(event)

    #Zonename and ZoneID, DynamoDB table
    host_zone_name = os.environ['HOST_ZONE_NAME']
    hostzone_id = os.environ['HOSTZONE_ID']
    record_type = os.environ['RECORD_TYPE']
    DynamoDB_table = os.environ['DYNAMODB_TABLE']

    # Get the instance id, ec2 information and tags from CW event
    instance_id = event['detail']['instance-id']
    LOGGER.debug("instance id: %s", str(instance_id) + lineno())
    state = event['detail']['state']
    LOGGER.debug("State: %s", str(state) + lineno())
    compute = get_ec2_client()
    instance_info = get_instance_info(compute, instance_id)
    LOGGER.debug("instance: %s", str(instance_info) + lineno())
    tags = instance_info['Reservations'][0]['Instances'][0]['Tags'][0]
    hostname = tags['Value']
    LOGGER.debug("Instance hostname: %s", str(hostname))


    # Update EC2 private IP to DynamoDB
    dynamodb_client = get_dynamodb_client()
    route53_client = get_route53_client()

    #If EC2 is running (start up) and it is not on DB table, update information to DB and create A record on Route 53 private zone, else don't do it and alarm.
    if state == 'running':
        items = query_hostname_in_dynamodb_table(dynamodb_client, DynamoDB_table, hostname)
        LOGGER.debug("Item return: %s", items)
        if  items['Count'] > 0:
            LOGGER.debug("DNS with this hostname is available on Route53 table")
            #SNS alarm shoud be sent here for hostname duplication notification.
        else:
            ec2_privateIP = instance_info['Reservations'][0]['Instances'][0]['PrivateIpAddress']
            LOGGER.debug("Putting instance private IP to DB and update to DNS: %s", str(ec2_privateIP))
            put_item_in_dynamodb_table(dynamodb_client, DynamoDB_table, hostname, ec2_privateIP, instance_id)
            # Update EC2 Private IP to route53 Private Zone
            change_resource_recordset(route53_client, hostzone_id,hostname, host_zone_name, record_type, ec2_privateIP,'UPSERT')
    #If EC2 is terminated, check if its instance_id on DB table, if match, remove it from DB and remove A record on Route 53 private zone, else don't do it and alarm.
    elif state == 'terminated':
        items = query_hostname_in_dynamodb_table(dynamodb_client, DynamoDB_table, hostname)
        if (items['Count'] == 0):
            LOGGER.debug("This hostname is not available on DB")
        else: 
            instance_id_store_on_DB = items['Items'][0]['instance_id']['S']
            ipaddress = items['Items'][0]['ipaddress']['S']
            if (instance_id == instance_id_store_on_DB):
                LOGGER.debug("Removing instance private IP out of DB and DNS: %s", ipaddress)
                 # Remove EC2 Private IP to route53 Private Zone
                change_resource_recordset(route53_client, hostzone_id,hostname, host_zone_name, record_type, ipaddress,'DELETE')
                # Remove EC2 Private IP in Dynamo DB 
                delete_item_in_dynamodb_table(dynamodb_client, DynamoDB_table, hostname)
            else:
                LOGGER.debug("This hostname is available but terminated EC2 instance id is not match, should not be deleted, instance_id stored in DB is %s, meanwhile termianted EC2 instance id is %s", instance_id_store_on_DB, instance_id)
