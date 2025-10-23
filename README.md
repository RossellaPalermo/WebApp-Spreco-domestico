#FoodFlow - Ecosistema Alimentare Intelligente
un'applicazione web moderna e intelligente per la gestione della dispensa domestica, progettata per ridurre gli sprechi alimentari attraverso AI, gamification e analytics avanzate.

## ✨ **Caratteristiche Principali**

### 🏠 **Dashboard Intelligente**
- Panoramica unificata del tuo ecosistema alimentare
- Notifiche smart per prodotti in scadenza
- Metriche in tempo reale su sprechi e risparmi
- Widget interattivi per accesso rapido

### 📦 **Gestione Dispensa**
- Monitoraggio automatico scadenze e scorte
- Categorizzazione intelligente dei prodotti
- Alert per prodotti in esaurimento
- Tracking storico degli acquisti

### 🤖 **AI & Ricette**
- Generazione ricette basate su ingredienti disponibili
- Suggerimenti personalizzati per prodotti in scadenza
- Integrazione Groq AI (LLaMA 3.3 70B)
- Ricette con valori nutrizionali dettagliati

### 🛒 **Lista Spesa Intelligente**
- Generazione automatica basata su consumi
- Suggerimenti AI per ottimizzare acquisti
- Sincronizzazione con piano pasti
- Storico liste e analisi spesa

### 📅 **Piano Nutrizionale**
- Calcolo BMR/TDEE personalizzato
- Obiettivi nutrizionali dinamici
- Tracking macro e micronutrienti
- Meal planning settimanale

### 📊 **Analytics Avanzate**
- Dashboard con grafici interattivi
- Report settimanali automatici
- Trend sprechi e risparmi
- Insights su abitudini alimentari

### 🎮 **Gamification**
- Sistema punti e livelli progressivi
- Badge e achievement
- Leaderboard globale
- Reward history completa

### 👨‍👩‍👧‍👦 **Sistema Famiglia**
- Creazione e gestione gruppi familiari
- Codice famiglia univoco per unirsi
- Condivisione prodotti e pasti tra membri
- Vista combinata contenuti personali + condivisi
- Gestione membri e ruoli (admin/membro)

### 🤝 **Sistema Sponsor & Partnership**
- Sezione sponsor nel footer e homepage
- Pagina dedicata per partnership commerciali
- Pacchetti sponsor (Starter, Professional, Enterprise)
- Form di contatto per potenziali partner
- Banner sponsor discreto per utenti non autenticati

---
## 🚀 **Installazione**

### **Prerequisiti**
- Python 3.8 o superiore
- MySQL Server 5.7+
- HeidiSQL (o altro client MySQL)

### **Setup Ambiente**

1. **Clone del repository**
2. **Creazione ambiente virtuale**
3. **Installazione dipendenze**
```bash
pip install -r requirements.txt
```
4. **Configurazione Database**
Crea il database MySQL:
```sql
CREATE DATABASE food_waste_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
5. **Configurazione variabili d'ambiente** (opzionale ma consigliato)
Crea un file `.env` nella root:
```bash
# .env
SECRET_KEY=la-tua-secret-key-super-sicura
DATABASE_URL=mysql+pymysql://root:root@localhost/food_waste_app?charset=utf8mb4
GROQ_API_KEY=la-tua-groq-api-key

Installa python-dotenv:
```bash
pip install python-dotenv
```
6. **Avvio applicazione**
```bash
python app.py
```

L'applicazione sarà disponibile su: `http://localhost:5000`
---

## 🎯 **Utilizzo**
### **1. Registrazione**
Crea un account su `/register`
### **2. Setup Profilo Nutrizionale**
Configura età, peso, altezza, obiettivi in `/nutritional-profile`
### **3. Aggiungi Prodotti**
Inserisci i prodotti della tua dispensa in `/products/add`
### **4. Ricevi Suggerimenti AI**
Nella dashboard, genera ricette intelligenti basate sui tuoi ingredienti
### **5. Pianifica Pasti**
Crea un piano settimanale in `/meal-planning`
### **6. Monitora Analytics**
Visualizza statistiche e report in `/analytics`
### **7. Gestisci Famiglia**
Crea o unisciti a una famiglia in `/family` per condividere prodotti e pasti
### **8. Diventa Partner**
Scopri opportunità di partnership in `/sponsors`
---

## 🛠️ **Tecnologie Utilizzate**
### **Backend**
- **Flask 3.0** - Framework web Python
- **SQLAlchemy** - ORM per database
- **Flask-Login** - Gestione autenticazione
- **PyMySQL** - Connector MySQL
### **Frontend**
- **Bootstrap 5.3** - UI framework
- **Bootstrap Icons** - Iconografia
- **AOS** - Animazioni scroll
- **Chart.js** - Grafici interattivi
### **AI & ML**
- **Groq API** - LLaMA 3.3 70B per ricette intelligenti
- **Requests** - HTTP client per API
### **Database**
- **MySQL 5.7+** - Database relazionale
---

## 📄 **Licenza**
Questo progetto è sotto licenza MIT. Vedi `LICENSE` per dettagli.
---

## 👨‍👩‍👧‍👦 **Sistema Famiglia - Dettagli**

### **Funzionalità Principali**
- **Creazione famiglia**: Un utente può creare una nuova famiglia con un nome personalizzato
- **Codice famiglia**: Ogni famiglia riceve un codice univoco di 12 caratteri (lettere maiuscole e numeri)
- **Unione a famiglia**: Gli utenti possono unirsi a una famiglia esistente inserendo il codice
- **Condivisione contenuti**: Prodotti e pasti possono essere marcati come "condivisi" e saranno visibili a tutti i membri
- **Vista combinata**: Ogni utente vede i propri contenuti + quelli condivisi dalla famiglia

### **Utilizzo Sistema Famiglia**
1. **Creare una Famiglia**: Vai su `/family` → "Crea Famiglia" → Inserisci nome → Copia il codice generato
2. **Unirsi a una Famiglia**: Vai su `/family` → "Unisciti a Famiglia" → Inserisci codice (12 caratteri)
3. **Condividere Prodotti/Pasti**: Attiva la checkbox "Condividi con la famiglia" nei form

### **API Endpoints Famiglia**
- `GET /family` - Pagina gestione famiglia
- `POST /family/create` - Crea nuova famiglia
- `POST /family/join` - Unisciti a famiglia
- `POST /family/leave` - Lascia famiglia
- `GET /family/members` - Lista membri famiglia

### **Modifiche Database**
Il sistema famiglia aggiunge le seguenti tabelle:
- `family` - Informazioni famiglia e codice univoco
- `family_member` - Relazione utenti-famiglia con ruoli
- Colonne `is_shared` aggiunte a `product` e `meal_plan`

---

## 👨‍💻 **Autore**
Rossella Palermo
- Email: s329788@studenti.polito.it
---
