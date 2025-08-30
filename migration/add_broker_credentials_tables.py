#!/usr/bin/env python3
"""
Migration script to add broker credentials tables to OpenAlgo database.

This script adds:
1. broker_api_credentials table - for system-wide broker API credentials
2. user_trading_credentials table - for user-specific trading credentials

Run this script after updating to the multi-broker version.
"""

import os
import sys
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Add the parent directory to the path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.broker_credentials_db import init_db, Base, engine
from utils.logging import get_logger

logger = get_logger(__name__)

def check_table_exists(engine, table_name):
    """Check if a table exists in the database"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='{table_name}'
            """))
            return result.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking if table {table_name} exists: {e}")
        return False

def create_broker_credentials_tables():
    """Create the new broker credentials tables"""
    try:
        logger.info("Starting broker credentials tables migration...")
        
        # Check if tables already exist
        broker_api_exists = check_table_exists(engine, 'broker_api_credentials')
        user_trading_exists = check_table_exists(engine, 'user_trading_credentials')
        
        if broker_api_exists and user_trading_exists:
            logger.info("Broker credentials tables already exist. Migration not needed.")
            return True
        
        if broker_api_exists or user_trading_exists:
            logger.warning("Only some broker credentials tables exist. This might indicate a partial migration.")
            response = input("Do you want to continue and create missing tables? (y/n): ")
            if response.lower() != 'y':
                logger.info("Migration cancelled by user.")
                return False
        
        # Create the tables
        logger.info("Creating broker credentials tables...")
        init_db()
        
        # Verify tables were created
        broker_api_exists_after = check_table_exists(engine, 'broker_api_credentials')
        user_trading_exists_after = check_table_exists(engine, 'user_trading_credentials')
        
        if broker_api_exists_after and user_trading_exists_after:
            logger.info("✅ Successfully created broker credentials tables")
            return True
        else:
            logger.error("❌ Failed to create some broker credentials tables")
            return False
            
    except SQLAlchemyError as e:
        logger.error(f"Database error during migration: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during migration: {e}")
        return False

def add_unique_constraint():
    """Add unique constraint to user_trading_credentials table"""
    try:
        logger.info("Adding unique constraint to user_trading_credentials...")
        
        with engine.connect() as conn:
            # Check if constraint already exists by trying to create a duplicate
            # SQLite doesn't have a direct way to check constraints, so we'll use a different approach
            
            # First, check if we can add the constraint by creating a unique index
            try:
                conn.execute(text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_user_trading_unique 
                    ON user_trading_credentials(user_id, broker_name)
                """))
                conn.commit()
                logger.info("✅ Successfully added unique constraint")
                return True
            except Exception as e:
                if "UNIQUE constraint failed" in str(e):
                    logger.warning("Unique constraint already exists or there are duplicate records")
                    return True
                else:
                    logger.error(f"Error adding unique constraint: {e}")
                    return False
                    
    except Exception as e:
        logger.error(f"Error adding unique constraint: {e}")
        return False

def verify_migration():
    """Verify that the migration was successful"""
    try:
        logger.info("Verifying migration...")
        
        # Check table structure
        with engine.connect() as conn:
            # Check broker_api_credentials table
            result = conn.execute(text("PRAGMA table_info(broker_api_credentials)"))
            broker_api_columns = [row[1] for row in result.fetchall()]
            
            expected_broker_api_columns = [
                'id', 'broker_name', 'api_key', 'api_secret', 
                'additional_config', 'is_active', 'created_at', 'updated_at'
            ]
            
            missing_broker_api = set(expected_broker_api_columns) - set(broker_api_columns)
            if missing_broker_api:
                logger.error(f"Missing columns in broker_api_credentials: {missing_broker_api}")
                return False
            
            # Check user_trading_credentials table
            result = conn.execute(text("PRAGMA table_info(user_trading_credentials)"))
            user_trading_columns = [row[1] for row in result.fetchall()]
            
            expected_user_trading_columns = [
                'id', 'user_id', 'broker_name', 'client_id', 'user_id_broker',
                'mobile_number', 'password', 'pin', 'totp_option', 'totp_secret',
                'additional_fields', 'is_active', 'created_at', 'updated_at'
            ]
            
            missing_user_trading = set(expected_user_trading_columns) - set(user_trading_columns)
            if missing_user_trading:
                logger.error(f"Missing columns in user_trading_credentials: {missing_user_trading}")
                return False
            
            logger.info("✅ All expected columns are present")
            return True
            
    except Exception as e:
        logger.error(f"Error verifying migration: {e}")
        return False

def main():
    """Main migration function"""
    logger.info("=" * 60)
    logger.info("OpenAlgo Broker Credentials Tables Migration")
    logger.info("=" * 60)
    
    # Check database connection
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False
    
    # Run migration steps
    steps = [
        ("Create broker credentials tables", create_broker_credentials_tables),
        ("Add unique constraints", add_unique_constraint),
        ("Verify migration", verify_migration)
    ]
    
    for step_name, step_func in steps:
        logger.info(f"\n--- {step_name} ---")
        if not step_func():
            logger.error(f"❌ Migration failed at step: {step_name}")
            return False
        logger.info(f"✅ {step_name} completed successfully")
    
    logger.info("\n" + "=" * 60)
    logger.info("🎉 Broker credentials tables migration completed successfully!")
    logger.info("=" * 60)
    logger.info("\nNext steps:")
    logger.info("1. Configure broker API credentials via admin interface")
    logger.info("2. Users can now set up their trading credentials for multiple brokers")
    logger.info("3. Test the new multi-broker authentication flow")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
