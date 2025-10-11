-- ============================================
-- FOODFLOW DATABASE SETUP SCRIPT
-- MariaDB/MySQL Database Creation Script
-- ============================================

-- Crea il database
CREATE DATABASE IF NOT EXISTS food_waste_app 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

-- Usa il database
USE food_waste_app;

-- ============================================
-- TABELLE PRINCIPALI
-- ============================================

-- Tabella utenti
CREATE TABLE IF NOT EXISTS `user` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(80) NOT NULL UNIQUE,
    `email` VARCHAR(120) NOT NULL UNIQUE,
    `password_hash` VARCHAR(255) NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_username` (`username`),
    INDEX `idx_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabella prodotti dispensa
CREATE TABLE IF NOT EXISTS `product` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `quantity` FLOAT NOT NULL,
    `unit` VARCHAR(20) NOT NULL,
    `expiry_date` DATE NOT NULL,
    `category` VARCHAR(50) NOT NULL,
    `min_quantity` FLOAT DEFAULT 1.0,
    `wasted` BOOLEAN DEFAULT FALSE,
    `allergens` VARCHAR(200) NULL,
    `notes` TEXT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_name` (`name`),
    INDEX `idx_expiry_date` (`expiry_date`),
    INDEX `idx_category` (`category`),
    INDEX `idx_wasted` (`wasted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabella liste spesa
CREATE TABLE IF NOT EXISTS `shopping_list` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `description` TEXT NULL,
    `store_name` VARCHAR(100) NULL,
    `budget` FLOAT NULL,
    `actual_spent` FLOAT DEFAULT 0.0,
    `completed` BOOLEAN DEFAULT FALSE,
    `is_smart` BOOLEAN DEFAULT FALSE,
    `is_template` BOOLEAN DEFAULT FALSE,
    `completed_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_completed` (`completed`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabella items lista spesa
CREATE TABLE IF NOT EXISTS `shopping_item` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `shopping_list_id` INT NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `quantity` FLOAT NOT NULL,
    `unit` VARCHAR(20) NOT NULL,
    `category` VARCHAR(50) NULL,
    `completed` BOOLEAN DEFAULT FALSE,
    `priority` INT DEFAULT 0,
    `estimated_price` FLOAT NULL,
    `notes` TEXT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`shopping_list_id`) REFERENCES `shopping_list`(`id`) ON DELETE CASCADE,
    INDEX `idx_shopping_list_id` (`shopping_list_id`),
    INDEX `idx_name` (`name`),
    INDEX `idx_category` (`category`),
    INDEX `idx_completed` (`completed`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- GAMIFICATION
-- ============================================

-- Tabella statistiche utente
CREATE TABLE IF NOT EXISTS `user_stats` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL UNIQUE,
    `points` INT DEFAULT 0,
    `level` INT DEFAULT 1,
    `total_products_added` INT DEFAULT 0,
    `total_products_wasted` INT DEFAULT 0,
    `total_shopping_lists` INT DEFAULT 0,
    `total_recipes_created` INT DEFAULT 0,
    `goals_achieved` INT DEFAULT 0,
    `waste_reduction_score` FLOAT DEFAULT 0.0,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabella badge
CREATE TABLE IF NOT EXISTS `badge` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(50) NOT NULL UNIQUE,
    `description` TEXT NULL,
    `icon` VARCHAR(50) NULL,
    `points_required` INT DEFAULT 0,
    `condition` VARCHAR(100) NULL,
    `category` VARCHAR(50) NOT NULL DEFAULT 'general'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabella badge utente
CREATE TABLE IF NOT EXISTS `user_badge` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `badge_id` INT NOT NULL,
    `earned_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`badge_id`) REFERENCES `badge`(`id`) ON DELETE CASCADE,
    UNIQUE KEY `unique_user_badge` (`user_id`, `badge_id`),
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_badge_id` (`badge_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabella cronologia ricompense
CREATE TABLE IF NOT EXISTS `reward_history` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `reward_type` VARCHAR(50) NOT NULL,
    `value` INT DEFAULT 0,
    `badge_id` INT NULL,
    `description` TEXT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`badge_id`) REFERENCES `badge`(`id`) ON DELETE SET NULL,
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- PIANO NUTRIZIONALE
-- ============================================

-- Tabella profilo nutrizionale
CREATE TABLE IF NOT EXISTS `nutritional_profile` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL UNIQUE,
    `age` INT NULL,
    `weight` FLOAT NULL,
    `height` FLOAT NULL,
    `gender` VARCHAR(10) DEFAULT 'male',
    `activity_level` VARCHAR(20) DEFAULT 'moderate',
    `goal` VARCHAR(20) DEFAULT 'maintain',
    `dietary_restrictions` TEXT NULL,
    `allergies` TEXT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabella obiettivi nutrizionali
CREATE TABLE IF NOT EXISTS `nutritional_goal` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL UNIQUE,
    `daily_calories` FLOAT NOT NULL,
    `daily_protein` FLOAT NOT NULL,
    `daily_carbs` FLOAT NOT NULL,
    `daily_fat` FLOAT NOT NULL,
    `daily_fiber` FLOAT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabella piano pasti
CREATE TABLE IF NOT EXISTS `meal_plan` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `date` DATE NOT NULL,
    `meal_type` VARCHAR(20) NOT NULL,
    `custom_meal` TEXT NULL,
    `calories` FLOAT NULL,
    `protein` FLOAT NULL,
    `carbs` FLOAT NULL,
    `fat` FLOAT NULL,
    `fiber` FLOAT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_date` (`user_id`, `date`),
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_date` (`date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabella nutrizione giornaliera
CREATE TABLE IF NOT EXISTS `daily_nutrition` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `date` DATE NOT NULL,
    `calories_consumed` FLOAT DEFAULT 0.0,
    `protein_consumed` FLOAT DEFAULT 0.0,
    `carbs_consumed` FLOAT DEFAULT 0.0,
    `fat_consumed` FLOAT DEFAULT 0.0,
    `fiber_consumed` FLOAT DEFAULT 0.0,
    `calories_goal` FLOAT DEFAULT 2000.0,
    `protein_goal` FLOAT DEFAULT 150.0,
    `carbs_goal` FLOAT DEFAULT 250.0,
    `fat_goal` FLOAT DEFAULT 65.0,
    `fiber_goal` FLOAT DEFAULT 25.0,
    `goal_completion_percentage` FLOAT DEFAULT 0.0,
    `consistency_score` FLOAT DEFAULT 0.0,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE,
    UNIQUE KEY `unique_daily_nutrition` (`user_id`, `date`),
    INDEX `idx_user_date_nutrition` (`user_id`, `date`),
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_date` (`date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- ANALYTICS
-- ============================================

-- Tabella analytics sprechi
CREATE TABLE IF NOT EXISTS `waste_analytics` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `date` DATE NOT NULL,
    `products_wasted` INT DEFAULT 0,
    `kg_wasted` FLOAT DEFAULT 0.0,
    `estimated_cost` FLOAT DEFAULT 0.0,
    `category_breakdown` TEXT NULL,
    `waste_trend` FLOAT DEFAULT 0.0,
    `most_wasted_category` VARCHAR(50) NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_date_waste` (`user_id`, `date`),
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_date` (`date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabella analytics shopping
CREATE TABLE IF NOT EXISTS `shopping_analytics` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `date` DATE NOT NULL,
    `items_purchased` INT DEFAULT 0,
    `estimated_cost` FLOAT DEFAULT 0.0,
    `category_breakdown` TEXT NULL,
    `ai_suggestions_used` INT DEFAULT 0,
    `most_purchased_category` VARCHAR(50) NULL,
    `shopping_frequency_days` FLOAT DEFAULT 0.0,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_date_shopping` (`user_id`, `date`),
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_date` (`date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- DATI INIZIALI
-- ============================================

-- Inserisci badge di default
INSERT IGNORE INTO `badge` (`name`, `description`, `icon`, `points_required`, `condition`, `category`) VALUES
('Benvenuto', 'Hai completato la registrazione', 'bi-star-fill', 0, 'registration', 'general'),
('Primo Passo', 'Hai aggiunto il primo prodotto', 'bi-box-seam', 10, 'first_product', 'general'),
('Eco-Warrior', 'Hai ridotto gli sprechi del 50%', 'bi-leaf', 100, 'waste_reduction_50', 'environment'),
('Chef Esperto', 'Hai creato 10 ricette', 'bi-egg-fried', 200, 'recipes_10', 'cooking'),
('Shopping Master', 'Hai completato 5 liste spesa', 'bi-cart-check-fill', 50, 'shopping_lists_5', 'shopping'),
('Nutrizionista', 'Hai seguito il piano nutrizionale per 30 giorni', 'bi-heart-pulse-fill', 300, 'nutrition_30_days', 'nutrition'),
('Pianificatore AI', 'Hai generato il primo piano pasti con AI', 'bi-robot', 25, 'ai_meal_plan_generated', 'ai'),
('Spreco Zero', 'Hai raggiunto una settimana senza sprechi', 'bi-recycle', 150, 'zero_waste_week', 'environment'),
('Consistenza', 'Hai seguito il piano nutrizionale per 7 giorni consecutivi', 'bi-calendar-check', 100, 'nutrition_consistency_7', 'nutrition'),
('Esploratore', 'Hai provato 5 nuove ricette', 'bi-compass', 75, 'new_recipes_5', 'cooking');

-- ============================================
-- VERIFICA SETUP
-- ============================================

-- Mostra le tabelle create
SHOW TABLES;

-- Mostra il numero di badge inseriti
SELECT COUNT(*) as 'Badge Inseriti' FROM badge;

-- Mostra informazioni database
SELECT 
    DATABASE() as 'Database Corrente',
    @@character_set_database as 'Charset',
    @@collation_database as 'Collation';

-- ============================================
-- NOTE FINALI
-- ============================================

/*
SETUP COMPLETATO!

Il database FoodFlow è stato creato con successo con:

✅ 12 tabelle principali
✅ Indici ottimizzati per performance
✅ Relazioni foreign key corrette
✅ 10 badge di default per gamification
✅ Charset UTF8MB4 per supporto emoji
✅ Engine InnoDB per transazioni ACID

PROSSIMI PASSI:
1. Configura le variabili d'ambiente (.env)
2. Avvia l'applicazione Flask
3. Crea il primo utente tramite registrazione
4. Inizia ad aggiungere prodotti alla dispensa

CONFIGURAZIONE RICHIESTA:
- SECRET_KEY: Chiave segreta per Flask
- DATABASE_URL: mysql+pymysql://user:password@localhost/food_waste_app
- GROQ_API_KEY: Chiave API per funzionalità AI

Buon lavoro con FoodFlow! 🚀
*/
