# Kiosque — voix off marketing

Voix de synthèse française **Valentin**, du catalogue Gradium. Choisie pour sa description de voix chaleureuse, vivante et adaptée à la publicité. Le texte parlé reprend les six paragraphes fournis par Jade. Les titres et les indications de réalisation ne sont pas lus.

## Fichiers à utiliser

- `Kiosque-voix-off-Gradium.mp3` : écoute et partage, 192 kbit/s.
- `Kiosque-voix-off-Gradium.wav` : piste complète pour le montage, PCM 16 bits, mono, 48 kHz.
- `Kiosque-6-passages-WAV.zip` : six fichiers WAV séparés, texte et repères temporels.
- `passages/` : les mêmes six fichiers, déjà décompressés.
- `chapitres.csv` : positions des six passages dans la piste complète.
- `script.txt` : texte prononcé, sans les indications visuelles.

Durée de la piste : **1 min 03,84 s**. Les respirations et le débit de la synthèse sont conservés. Une courte pause sépare chaque partie. Aucun fond musical ni effet sonore n’a été ajouté.

## Traitement et vérification

Les six paragraphes sont générés séparément avec la même voix et les mêmes réglages. Le volume est relevé de 2,48 dB par un gain constant, sans compression ni modification de vitesse. Mesure de la piste complète : **−16,08 LUFS**, crête vraie **−1,50 dBTP**. La source WAV reste disponible dans `sources/`.

Le contrôle de transcription est effectué localement avec Whisper base ; ses résultats sont dans `verification-transcription.txt` et `.json`. Ce contrôle automatique aide à vérifier le contenu mais ne remplace pas une appréciation humaine du jeu de voix.

## Reproduction

`generate.py generate` utilise la variable `GRADIUM_API_KEY`, ou celle du fichier `.env` à la racine du projet. Le script n’affiche pas la clé et ne réécrit pas les fichiers sources existants. Les réglages de chaque requête, sans clé, sont conservés dans `sources/*.request.json`.

`finish.py assemble` assemble et exporte les fichiers avec FFmpeg. `finish.py transcribe` utilise uniquement le modèle local `/private/tmp/kiosque-whisper-base` et le paquet temporaire faster-whisper. Ces dépendances de contrôle ne sont pas nécessaires pour utiliser les fichiers audio.

Voix : `WWHSNJCSTm77dyGd` (Valentin). Modèle TTS : `default`. Température : 0,65. `padding_bonus` : 0,1. Normalisation textuelle : `fr`.

Documentation : [synthèse Gradium REST](https://docs.gradium.ai/guides/text-to-speech-rest), [réglages de voix](https://docs.gradium.ai/guides/voice-settings), [catalogue de voix](https://docs.gradium.ai/api-reference/endpoint/get-voices), [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
