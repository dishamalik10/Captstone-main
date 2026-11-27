-- Schema created by database.init_database() at commit c59a86a (first audit).
-- Used by tests/test_characterisation.py to check that today's migrations upgrade it.
CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT,
                email TEXT UNIQUE,
                password_hash TEXT,
                avatar_url TEXT,
                location TEXT NOT NULL DEFAULT '',
                profile_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

CREATE TABLE preferences (
                user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                preferred_colors TEXT NOT NULL DEFAULT '[]',
                avoided_colors TEXT NOT NULL DEFAULT '[]',
                preferred_styles TEXT NOT NULL DEFAULT '[]',
                disliked_styles TEXT NOT NULL DEFAULT '[]',
                fit_preference TEXT,
                updated_at TEXT NOT NULL
            );

CREATE TABLE clothing_items (
                item_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                garment_group TEXT NOT NULL,
                color_name TEXT NOT NULL,
                image_path TEXT NOT NULL,
                confidence TEXT NOT NULL,
                pattern TEXT,
                fabric TEXT,
                fit TEXT,
                texture TEXT,
                seasons TEXT NOT NULL DEFAULT '[]',
                style_tags TEXT NOT NULL DEFAULT '[]',
                occasion_tags TEXT NOT NULL DEFAULT '[]',
                available INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            , embedding BLOB);

CREATE TABLE recommendations (
                recommendation_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                occasion TEXT NOT NULL,
                item_ids TEXT NOT NULL,
                component_scores TEXT NOT NULL,
                total_score REAL NOT NULL,
                explanation TEXT NOT NULL,
                run_id TEXT,
                rank_position INTEGER,
                created_at TEXT NOT NULL
            );

CREATE TABLE feedback (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                recommendation_id TEXT,
                item_ids TEXT NOT NULL,
                action TEXT NOT NULL,
                rating INTEGER,
                created_at TEXT NOT NULL
            );

CREATE TABLE sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

CREATE TABLE products (
                product_id TEXT PRIMARY KEY,
                seller_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                price REAL NOT NULL,
                image_urls TEXT NOT NULL DEFAULT '[]',
                category TEXT NOT NULL,
                condition TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            );

CREATE TABLE orders (
                order_id TEXT PRIMARY KEY,
                buyer_id TEXT NOT NULL REFERENCES users(user_id),
                seller_id TEXT NOT NULL REFERENCES users(user_id),
                product_id TEXT NOT NULL REFERENCES products(product_id),
                amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            );

CREATE TABLE social_posts (
                post_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                outfit_image_url TEXT NOT NULL,
                caption TEXT NOT NULL,
                product_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );

CREATE TABLE post_likes (
                post_id TEXT NOT NULL REFERENCES social_posts(post_id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                PRIMARY KEY(post_id, user_id)
            );

CREATE TABLE follows (
                follower_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                followed_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                PRIMARY KEY(follower_id, followed_id)
            );

CREATE TABLE chat_messages (
                message_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                session_id TEXT NOT NULL DEFAULT 'legacy',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

CREATE INDEX ix_clothing_user
            ON clothing_items(user_id, available, category);

CREATE INDEX ix_recommendations_run ON recommendations(run_id, rank_position);

CREATE INDEX ix_feedback_recommendation ON feedback(recommendation_id, created_at);
