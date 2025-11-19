"""
AWS Systems Manager Parameter Store utility
Provides functions to fetch parameters from AWS SSM
"""
import boto3
from botocore.exceptions import ClientError
from typing import Optional
import os


def get_ssm_parameter(parameter_name: str) -> Optional[str]:
    """
    Fetch a parameter from AWS Systems Manager Parameter Store

    Args:
        parameter_name: The name/path of the parameter (e.g., '/cloud_cost_aggregator/AZURE_SPONSORSHIP_COOKIES')

    Returns:
        The parameter value as a string, or None if not found

    Raises:
        ClientError: If there's an error accessing AWS SSM
    """
    try:
        # Use AWS credentials from environment variables
        session_kwargs = {
            'aws_access_key_id': os.getenv('AWS_ACCESS_KEY_ID'),
            'aws_secret_access_key': os.getenv('AWS_SECRET_ACCESS_KEY'),
            'region_name': os.getenv('ap-south-1')
        }

        # Create SSM client
        ssm = boto3.client('ssm', **session_kwargs)

        # Get the parameter with decryption enabled
        response = ssm.get_parameter(
            Name=parameter_name,
            WithDecryption=True
        )

        return response['Parameter']['Value']

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ParameterNotFound':
            raise ValueError(f"Parameter '{parameter_name}' not found in AWS Systems Manager")
        else:
            raise Exception(f"Error fetching parameter from AWS SSM: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error fetching parameter from AWS SSM: {e}")
