import re
from collections import Counter


class AIService:
    """Service d'analyse IA pour les psychologues."""

    MENTAL_HEALTH_KEYWORDS = [
        'anxiété', 'anxieux', 'anxieuse', 'dépression', 'déprimé', 'triste', 'tristesse',
        'peur', 'peureux', 'colère', 'colérique', 'énervé', 'insomnie', 'fatigue',
        'désespoir', 'solitude', 'abandon', 'suicide', 'mort', 'automutilation',
        'crise', 'panique', 'inquiétude', 'inquiet', 'angoisse', 'stress',
        'sentiment', 'émotion', 'conflit', 'difficulté', 'problème', 'maladie',
        'douleur', 'cancer', 'hôpital', 'médecin', 'traitement', 'médicament'
    ]

    POSITIVE_KEYWORDS = [
        'mieux', 'espoir', 'progrès', 'content', 'heureux', 'calme', 'serein',
        'confiance', 'acceptation', 'gratitude', 'sourire', 'joie', 'optimisme',
        'amelioration', 'ameliorée', 'réussite', 'succès', 'fatigue diminuée'
    ]

    RISK_KEYWORDS = [
        'suicide', 'me tuer', 'plus supporter', 'finir mes jours',
        'automutilation', 'me faire mal', 'désespéré', 'désespoir',
        'je vais mourir', 'pas envie de vivre', 'vivre ne sert à rien',
        'inutile de vivre', 'meurtre', 'tuer quelqu\'un', 'blesser',
        'blessure', 'couper', 'brûler', 'pendaison', 'overdose', 'overdose'
    ]

    EMOTION_KEYWORDS = {
        'tristesse': ['triste', 'pleure', 'malheureux', 'désespéré', 'désespoir', 'abattu', 'découragé'],
        'anxiété': ['anxieux', 'inquiète', 'stress', 'panique', 'peur', 'angoisse', 'nerveux', 'tendu'],
        'colère': ['colère', 'énervé', 'furieux', 'irrité', 'fâché', 'rage', 'agacé'],
        'joie': ['heureux', 'content', 'joyeux', 'sourire', 'excité', 'enthousiaste', 'satisfait'],
        'peur': ['peur', 'effrayé', 'terrifié', 'anxieux', 'phobie', 'menace', 'danger'],
        'fatigue': ['fatigué', 'épuisé', 'crevé', 'exhaust', 'manque d\'énergie'],
        'espoir': ['espoir', 'optimiste', 'confiant', 'sûr', 'persévérer']
    }

    @staticmethod
    def analyze_keywords(text):
        """Extrait et compte les mots-clés de santé mentale d'un texte."""
        if not text:
            return {'keywords': [], 'count': 0, 'negative_count': 0, 'positive_count': 0}

        text_lower = text.lower()
        found_keywords = []
        negative_found = []
        positive_found = []

        for keyword in AIService.MENTAL_HEALTH_KEYWORDS:
            if keyword in text_lower:
                found_keywords.append(keyword)
                negative_found.append(keyword)

        for keyword in AIService.POSITIVE_KEYWORDS:
            if keyword in text_lower:
                found_keywords.append(keyword)
                positive_found.append(keyword)

        return {
            'keywords': list(set(found_keywords)),
            'count': len(set(found_keywords)),
            'negative_count': len(set(negative_found)),
            'positive_count': len(set(positive_found))
        }

    @staticmethod
    def generate_session_summary(messages):
        """Génère un résumé à partir des messages d'une conversation."""
        if not messages:
            return "Aucun message dans cette session."

        all_text = ' '.join([
            msg.get('content', '') or msg.get('contenu', '') or ''
            for msg in messages
        ])

        keyword_analysis = AIService.analyze_keywords(all_text)

        summary_parts = []

        if keyword_analysis['count'] > 0:
            summary_parts.append(
                f"Thèmes abordés: {', '.join(keyword_analysis['keywords'][:10])}"
            )

        if keyword_analysis['negative_count'] > keyword_analysis['positive_count']:
            summary_parts.append("Tonalité générale: Plutôt négative/difficile")
        else:
            summary_parts.append("Tonalité générale: Plutôt positive/constructive")

        summary_parts.append(f"Nombre de messages analysés: {len(messages)}")

        return '\n'.join(summary_parts)

    @staticmethod
    def detect_emotions(text):
        """Détecte les émotions dans un texte."""
        if not text:
            return []

        text_lower = text.lower()
        emotions = []

        for emotion, keywords in AIService.EMOTION_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                emotions.append(emotion)

        return emotions

    @staticmethod
    def detect_risk_level(text):
        """Évalue le niveau de risque à partir d'un texte."""
        if not text:
            return {'level': 'low', 'color': 'green', 'message': 'Risque faible'}

        text_lower = text.lower()
        risk_score = 0

        for keyword in AIService.RISK_KEYWORDS:
            if keyword in text_lower:
                risk_score += 2

        if risk_score >= 4:
            return {
                'level': 'high',
                'color': 'red',
                'message': 'Risque élevé détecté - Intervention recommandée'
            }
        elif risk_score >= 2:
            return {
                'level': 'medium',
                'color': 'orange',
                'message': 'Risque modéré - Surveillance recommandée'
            }
        else:
            return {'level': 'low', 'color': 'green', 'message': 'Risque faible'}