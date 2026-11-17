CREATE TABLE "customer" ("id" INTEGER PRIMARY KEY,"name" TEXT,"group" TEXT,"region" TEXT,"joined_at" TEXT,"credit" REAL);
CREATE TABLE "order" ("id" INTEGER PRIMARY KEY,"customer_id" INTEGER,"group" TEXT,"amount" REAL,"note" TEXT,"created_at" TEXT,"select" TEXT);
