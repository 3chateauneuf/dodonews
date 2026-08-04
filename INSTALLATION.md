# 🌅 DodoNews - Guide d'Installation

## 📋 Ce que tu as

✅ `agregador.py` - Script Python  
✅ `requirements.txt` - Dépendances  
✅ `.env.example` - Configuration  
✅ `.github/workflows/dodonews.yml` - Automatisation  
✅ `README.md` - Documentation

## 🚀 5 Minutes pour Commencer

### Étape 1: Obtenir ta clé API
1. Va sur https://console.anthropic.com
2. Copie ta clé (commence par `sk-ant-`)

### Étape 2: Créer `.env`
```bash
cp .env.example .env
```

Edite `.env`:
```
ANTHROPIC_API_KEY=sk-ant-ta-clé-ici
```

### Étape 3: Installer Python (si nécessaire)
Télécharge depuis https://www.python.org

### Étape 4: Exécuter
```bash
pip install -r requirements.txt
python agregador.py
```

### Étape 5: Voir le résultat
Ouvre `output/index.html` dans ton navigateur

**C'est tout! 🎉**

---

## 🤖 Automatisation GitHub (10 minutes)

### 1. Créer un repo GitHub
- Va sur https://github.com/new
- Nom: `dodonews`
- Public (pour Pages)

### 2. Pousser le code
```bash
git config user.name "Ton Nom"
git config user.email "ton@email.com"
git init
git add -A
git commit -m "Initial commit: DodoNews"
git branch -M main
git remote add origin https://github.com/TonUser/dodonews.git
git push -u origin main
```

### 3. Configurer le Secret
1. GitHub → Settings → Secrets and variables → Actions
2. New repository secret
3. Name: `ANTHROPIC_API_KEY`
4. Value: `sk-ant-ta-clé`

### 4. Tester
- Va à Actions
- Click "Run workflow"
- Attends 30 secondes

### 5. Pages (optionnel)
- Settings → Pages
- Source: "GitHub Actions"
- Ton site: `TonUser.github.io/dodonews`

---

## 🎨 Personnaliser

### L'heure du matin
`.github/workflows/dodonews.yml`:
```yaml
- cron: '0 7 * * *'  # Changer 7 par ton heure
```

Exemples:
- `'0 8 * * *'` = 8h chaque jour
- `'0 */6 * * *'` = Toutes les 6h
- Générateur: https://crontab.guru

### Plus de nouvelles par région
`agregador.py` - Section `FEEDS`:
```python
FEEDS = {
    "France": [
        "https://source1.fr/rss.xml",
        "https://source2.fr/rss.xml",  # Ajoute ici
    ],
}
```

### Longueur des résumés
`agregador.py` - Prompt Claude (ligne ~42):
```python
# Change "30 mots" à "50 mots"
```

---

## ❓ Problèmes?

### "ANTHROPIC_API_KEY not found"
- Vérifi que `.env` existe
- Contient: `ANTHROPIC_API_KEY=sk-ant-...`
- Pas d'espaces autour du `=`

### "No module named 'feedparser'"
```bash
pip install -r requirements.txt
```

### GitHub Actions échoue
- Va à Actions → Click sur la ligne rouge
- Lis le message d'erreur
- Probablement: Secret mal configuré

---

## 📊 Résumé

| Étape | Temps | Difficulté |
|-------|-------|-----------|
| Config locale | 5 min | Très facile |
| GitHub | 5 min | Facile |
| Automatisation | 5 min | Facile |
| **TOTAL** | **15 min** | **Débutant** |

---

## ✅ Checklist Final

- [ ] `.env` créé avec API key
- [ ] `python agregador.py` fonctionne
- [ ] `output/index.html` généré
- [ ] Repo GitHub créé
- [ ] Code pushé
- [ ] Secret `ANTHROPIC_API_KEY` configuré
- [ ] GitHub Actions exécuté avec ✅
- [ ] Pages activées (optionnel)

**Une fois tout coché, tu es prêt!** 🚀

---

**Bon matin avec DodoNews!** ☕
