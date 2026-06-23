# 🎬 Mastering YouTube Pro - Guide Rapide

## 🎯 Qu'est-ce que le Mastering YouTube ?

Le mastering optimisé YouTube prépare ton son pour une diffusion parfaite sur la plateforme :

### ✅ Ce qui est fait automatiquement :

1. **Lissage des défauts**
   - De-esser (réduit les sifflantes)
   - Noise Gate (élimine le bruit de fond)
   - Coupe des sub-bass parasites (< 30 Hz)

2. **Normalisation LUFS -14**
   - Standard YouTube officiel
   - Volume optimal pour tous les appareils
   - Évite la réduction automatique de YouTube

3. **True Peak -1.0 dB**
   - Évite la distorsion pendant le streaming
   - Marge de sécurité pour l'encodage MP3/AAC

4. **Compression professionnelle**
   - Lisse les variations de volume
   - Punch et présence améliorés
   - Limiteur final pour éviter le clipping

---

## 🚀 3 Façons d'utiliser le Mastering

### 1️⃣ Interface Web (Recommandé)

1. Lance `LANCER_STUDIO_IA.bat`
2. Ouvre http://localhost:8000 dans ton navigateur
3. Clique sur **"🎬 Mastering YouTube"**
4. Sélectionne ton fichier (WAV, MP3, M4A)
5. Télécharge le résultat masterisé en 30 secondes !

**Avantage** : Le plus simple, avec aperçu visuel

---

### 2️⃣ Drag & Drop (Ultra rapide)

1. Glisse-dépose ton fichier audio sur `master_youtube.bat`
2. Choisis **[S]tandard** ou **[C]reatif**
3. Le fichier masterisé apparaît dans le même dossier
4. Suffixe ajouté : `_MASTERED_YT.wav`

**Avantage** : Aucun clic, juste drag & drop !

---

### 3️⃣ Ligne de commande (Avancé)

```bash
# Mastering standard
python utils\youtube_mastering.py "mon_fichier.wav"

# Mastering créatif (boost vocal + stereo)
python utils\youtube_mastering.py "mon_fichier.wav" --creative
```

**Avantage** : Scriptable, intégrable dans ton workflow

---

## 🎨 Mode Standard vs Créatif

### Mode Standard (Recommandé)
- Mastering transparent et professionnel
- Respecte le mixage original
- Idéal pour : hip-hop, électro, pop, rock

### Mode Créatif (Expérimental)
- Boost des médiums (voix plus présentes)
- Élargissement stéréo (son plus large)
- Compression plus agressive
- Idéal pour : rap, trap, drill, R&B

---

## 📊 Résultats Garantis

| Paramètre | Avant | Après |
|-----------|-------|-------|
| **LUFS** | Variable (-8 à -20) | **-14.0** |
| **True Peak** | Risque de 0 dBFS | **-1.0 dB** |
| **Bruit de fond** | Audible | **Réduit** |
| **Clipping** | Possible | **Éliminé** |
| **Compatibilité YouTube** | ❌ | ✅ |

---

## 🎯 Formats Supportés

**Entrée** : WAV, MP3, M4A, FLAC, AIFF, OGG  
**Sortie** : WAV 32-bit float (haute qualité)

---

## 💡 Conseils Pro

### ✅ À FAIRE :
- Exporte ton mixage à -6 dBFS de headroom (pas compressé à bloc)
- Laisse de la dynamique dans ton mixage
- Utilise des stems de bonne qualité (pas de MP3 128 kbps)

### ❌ À ÉVITER :
- Ne masterise PAS un son déjà masterisé (double compression)
- N'applique PAS de limiteur avant le mastering
- Ne normalise PAS manuellement avant le mastering

---

## 🔧 Paramètres Techniques

```python
Chaîne de traitement :
1. Highpass Filter (30 Hz)
2. Noise Gate (-40 dB)
3. Compressor (threshold -18 dB, ratio 3:1)
4. Gain automatique (pour atteindre -14 LUFS)
5. Limiter final (-1.0 dB)
```

---

## 📁 Où sont sauvegardés les fichiers ?

### Interface Web :
```
C:\Users\moi\Desktop\music prete\Mastered\
```

### Drag & Drop / CLI :
```
Même dossier que le fichier source
Suffixe : _MASTERED_YT.wav
```

---

## 🐛 Problèmes Courants

### "Fichier introuvable"
→ Vérifie que le chemin ne contient pas de caractères spéciaux

### "Erreur pyloudnorm"
→ Installe la dépendance : `pip install pyloudnorm`

### "Le son est trop fort / trop faible"
→ Normal : YouTube ajuste automatiquement à -14 LUFS

---

## 📞 Support

Besoin d'aide ? Ouvre une issue sur GitHub ou contacte le support.

---

**Fait avec ❤️ par Studio IA**  
*Mastering professionnel en 30 secondes* 🚀
