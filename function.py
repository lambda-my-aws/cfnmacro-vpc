# -*- coding: utf-8 -*-

""" cfnmacro-vpc """

import json
import boto3
from subnets_maths import get_subnet_layers
from vpc import generate_vpc_template


def lambda_handler(event, context):
    """
    cfnmacro-vpc Lambda Handler
    """

    response = {
        "status": "success",
        "requestId": event['requestId']
    }
    region = event['region']
    account_id = event['accountId']
    transform_id = event['transformId']
    fragment = event['fragment']
    params = event['params']
    param_values = event['templateParameterValues']

    azs = boto3.client('ec2', region_name=region).describe_availability_zones(
        Filters=[
            {
                'Name': 'state',
                'Values': ['available']
            }
        ]
    )['AvailabilityZones']

    azs_count = len(azs)
    cidr_block = param_values['VpcCidr']
    layers = get_subnet_layers(cidr_block, azs_count)
    vpc_template = generate_vpc_template(layers, range(0, azs_count), cidr_block)
    resources = vpc_template.to_dict()['Resources']
    fragment['Resources'] = resources
    response['fragment'] = fragment
    print(response.keys())
    print(response['requestId'])
    print(response['status'])
    return response

if __name__ == '__main__':
    ret = lambda_handler(
        {
            'region': 'eu-west-1',
            'accountId': '123456789012',
            'requestId': 'notimportant',
            'transformId': '',
            'fragment': {},
            'params': {},
            'templateParameterValues': {'VpcCidr': '10.242.0.0/22'}
        },
        None
    )
    print(ret)
