#!/usr/bin/env python3
"""
Create Production User for Analytics
Create a real user account for analytics integration
Version 1.0.0 - September 27, 2025
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trading_analytics import auth

def create_production_user():
    """Create a production user account"""
    print("🚀 Creating Production Analytics User")
    print("=" * 50)
    
    # Get user input
    username = input("Enter username: ").strip()
    if not username:
        print("❌ Username required")
        return False
    
    email = input("Enter email: ").strip()
    if not email or '@' not in email:
        print("❌ Valid email required")
        return False
    
    password = input("Enter password (min 8 chars): ").strip()
    if not password or len(password) < 8:
        print("❌ Password must be at least 8 characters")
        return False
    
    # Create user
    print(f"\n📝 Creating user account...")
    success, message = auth.register_user(username, email, password)
    
    if success:
        print(f"✅ User created successfully!")
        print(f"   Username: {username}")
        print(f"   Email: {email}")
        print(f"   Password: {'*' * len(password)}")
        
        # Test authentication
        print(f"\n🔐 Testing authentication...")
        user_info = auth.authenticate_user(username, password)
        
        if user_info:
            print(f"✅ Authentication successful!")
            print(f"   User ID: {user_info['id']}")
            print(f"   Subscription: {user_info['subscription_tier']}")
            
            print(f"\n🎉 **Setup Complete!**")
            print(f"📊 You can now:")
            print(f"   1. Login to analytics dashboard with: {username} / {password}")
            print(f"   2. Use analytics tab in main trading GUI")
            print(f"   3. Auto-track generated signals")
            
            return True
        else:
            print(f"❌ Authentication test failed")
            return False
    else:
        print(f"❌ {message}")
        return False

def show_existing_users():
    """Show existing users in database"""
    try:
        from trading_analytics import db
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, username, email, subscription_tier, created_at FROM users")
        users = cursor.fetchall()
        
        if users:
            print("📋 Existing Users:")
            print("-" * 60)
            for user in users:
                print(f"ID: {user[0]} | User: {user[1]} | Email: {user[2]} | Tier: {user[3]} | Created: {user[4]}")
        else:
            print("📋 No users found in database")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Failed to show users: {e}")

def main():
    """Main user creation interface"""
    print("🎯 Analytics User Management")
    print("=" * 50)
    
    while True:
        print("\nOptions:")
        print("1. Create new user")
        print("2. Show existing users")
        print("3. Exit")
        
        choice = input("\nSelect option (1-3): ").strip()
        
        if choice == '1':
            create_production_user()
        elif choice == '2':
            show_existing_users()
        elif choice == '3':
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid option")

if __name__ == "__main__":
    main()