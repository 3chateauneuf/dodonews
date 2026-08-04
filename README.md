# 🌅 DodoNews

**Les infos du matin en quelques mots**

Un agrégateur minimaliste de nouvelles en français pour lire après le dodo.

## ⚡ Caractéristiques

✅ Résumés ultra-courts (30 mots max)  
✅ Mis à jour chaque matin à 7h UTC  
✅ 3 régions: France, Île-de-France, Chili  
✅ Design minimaliste et rapide à charger  
✅ Aucun coût (utilise ton Claude Max)

## 🚀 Installation Rapide

### 1. Cloner
```bash
git clone https://github.com/ton-user/dodonews.git
cd dodonews
```

### 2. Configurer
```bash
cp .env.example .env
# Ajoute ta clé API Anthropic dans .env
```

### 3. Tester
```bash
pip install -r requirements.txt
python agregador.py
```

Ouvre `output/index.html`

## 🤖 Automatisation GitHub

1. Crée un repo public sur GitHub
2. Pousse le code
3. Settings → Secrets → Ajoute `ANTHROPIC_API_KEY`
4. Active GitHub Pages
5. C'est tout! Se met à jour chaque matin à 7h

## 📝 Personnalisation

### Changer l'heure
Edite `.github/workflows/dodonews.yml`:
```yaml
- cron: '0 9 * * *'  # 9h au lieu de 7h
```

### Ajouter des sources
Edite `agregador.py`, section `FEEDS`:
```python
FEEDS = {
    "France": [
        "https://nouvelle-source.com/rss.xml",
    ],
}
```

## 📱 Affichage

La page se charge en < 1 seconde sur mobile.

Conçu pour:
- ✅ Smartphone au réveil
- ✅ Café le matin
- ✅ Lecture de 2 minutes max

## 💬 Format

**DodoNews** = Minimaliste + Rapide + Français

Pas de catégories, pas de labels. Juste les faits.

---

**Fait avec ❤️ et Claude**
