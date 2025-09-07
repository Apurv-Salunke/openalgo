# utils/broker_resolver.py

"""
Broker resolver utility for OpenAlgo multi-broker system.

This module provides centralized logic for resolving broker selection and
authentication tokens, maintaining backward compatibility while enabling
multi-broker functionality.
"""

from typing import Tuple, Optional
from database.auth_db import (
    verify_api_key, 
    get_auth_token_by_broker, 
    get_user_default_broker,
    get_user_brokers
)
from utils.logging import get_logger

logger = get_logger(__name__)

def resolve_broker_and_tokens(api_key: str, requested_broker: Optional[str] = None) -> Tuple[str, str, Optional[str]]:
    """
    Resolve broker selection and get authentication tokens.
    
    This is the central integration point for broker selection logic.
    It handles both single-broker (backward compatible) and multi-broker scenarios.
    
    Args:
        api_key: User's API key
        requested_broker: Optional broker name (e.g., 'angel', 'zerodha', 'upstox')
        
    Returns:
        Tuple of (broker_name, auth_token, feed_token)
        
    Raises:
        ValueError: If broker is not configured for user or API key is invalid
    """
    try:
        # Verify API key and get user_id
        user_id = verify_api_key(api_key)
        if not user_id:
            raise ValueError("Invalid API key")
        
        logger.debug(f"Resolving broker for user {user_id}, requested_broker: {requested_broker}")
        
        if requested_broker:
            # Multi-broker mode: get token for specific broker
            auth_token = get_auth_token_by_broker(user_id, requested_broker)
            if not auth_token:
                # Check if user has any brokers configured
                user_brokers = get_user_brokers(user_id)
                if not user_brokers:
                    raise ValueError("No brokers configured for this user")
                else:
                    available_brokers = ", ".join(user_brokers)
                    raise ValueError(f"Broker '{requested_broker}' not configured for this user. Available brokers: {available_brokers}")
            
            # Get feed token for the specific broker
            from database.auth_db import get_feed_token_by_broker
            feed_token = get_feed_token_by_broker(user_id, requested_broker)
            
            logger.info(f"Resolved broker '{requested_broker}' for user {user_id}")
            return requested_broker, auth_token, feed_token
            
        else:
            # Backward compatible mode: use existing logic
            from database.auth_db import get_auth_token_broker
            result = get_auth_token_broker(api_key, include_feed_token=True)
            
            if len(result) == 3:
                auth_token, feed_token, broker_name = result
            else:
                auth_token, broker_name = result
                feed_token = None
            
            if not auth_token or not broker_name:
                raise ValueError("No valid authentication found for this API key")
            
            logger.info(f"Resolved default broker '{broker_name}' for user {user_id}")
            return broker_name, auth_token, feed_token
            
    except ValueError:
        # Re-raise ValueError as-is (these are expected business logic errors)
        raise
    except Exception as e:
        logger.error(f"Error resolving broker and tokens: {e}")
        raise ValueError(f"Error resolving broker authentication: {str(e)}")

def get_user_broker_list(api_key: str) -> list:
    """
    Get list of brokers configured for a user.
    
    Args:
        api_key: User's API key
        
    Returns:
        List of broker names configured for the user
        
    Raises:
        ValueError: If API key is invalid
    """
    try:
        user_id = verify_api_key(api_key)
        if not user_id:
            raise ValueError("Invalid API key")
        
        brokers = get_user_brokers(user_id)
        logger.debug(f"User {user_id} has brokers: {brokers}")
        return brokers
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error getting user broker list: {e}")
        raise ValueError(f"Error getting user broker list: {str(e)}")

def validate_broker_for_user(api_key: str, broker_name: str) -> bool:
    """
    Validate that a broker is configured for a user.
    
    Args:
        api_key: User's API key
        broker_name: Broker name to validate
        
    Returns:
        True if broker is configured for user, False otherwise
    """
    try:
        user_id = verify_api_key(api_key)
        if not user_id:
            return False
        
        user_brokers = get_user_brokers(user_id)
        return broker_name in user_brokers
        
    except Exception as e:
        logger.error(f"Error validating broker for user: {e}")
        return False
