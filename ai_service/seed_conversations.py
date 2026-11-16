# -*- coding: utf-8 -*-
"""
Script de generation de donnees de test pour l'integration IA.
Genere 30 scenarios x 3 langues = 90 conversations, chacune avec 14 messages
(7 patient / 7 psychologue, alternes, commencant par le patient).
Total : environ 1260 messages.

Ce script NE modifie aucun fichier existant du projet. Il cree uniquement des
enregistrements en base via l'ORM Django (CustomUser, Conversation, Message).

Usage : python seed_conversations.py
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mindwell.settings")

# Ajouter le repertoire parent au PYTHONPATH si necessaire
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django  # noqa: E402

django.setup()  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from accounts.models import Conversation, Message  # noqa: E402

CustomUser = get_user_model()

# ---------------------------------------------------------------------------
# 30 scenarios de conversation. Chaque scenario contient 14 messages alternes
# (patient, psychologue, patient, psychologue, ...).
# Chaque message possede un contenu en 3 langues : fr, ar, en.
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        "id": 1,
        "theme": "Anxiété généralisée",
        "keywords_fr": ["anxiété", "inquiétude", "stress", "tension"],
        "messages": [
            ("patient", "Je me sens tout le temps sur le qui-vive, comme si quelque chose de terrible allait arriver.", "أشعر أنني على أهبة الاستعداد طوال الوقت، كأن شيئاً terribles سيحدث.", "I feel constantly on edge, as if something terrible is going to happen."),
            ("psychologue", "Bonjour. Merci d'avoir partagé cela. Depuis combien de temps ressentez-vous cette tension ?", "أهلاً بك. شكراً على مشاركتك هذا. منذ متى تشعر بهذا التوتر؟", "Hello. Thank you for sharing that. How long have you been feeling this tension?"),
            ("patient", "Cela fait plusieurs mois. Je dors mal et je m'inquiète pour tout, même les petites choses.", "منذ عدة أشهر. أنام بشكل سيئ وأقلق بشأن كل شيء، حتى الأمور الصغيرة.", "It's been several months. I sleep poorly and worry about everything, even small things."),
            ("psychologue", "Je comprends. L'anxiété peut envahir le quotidien. Quelles situations déclenchent le plus cette inquiétude chez vous ?", "أفهم. القلق يمكن أن يغزو الحياة اليومية. ما هي المواقف التي تثير هذا القلق أكثر لديك؟", "I understand. Anxiety can invade daily life. Which situations trigger the most worry for you?"),
            ("patient", "Principalement le travail et les relations sociales. J'ai peur d'être jugé ou de faire une erreur.", "بشكل رئيسي العمل والعلاقات الاجتماعية. أخشى أن أُحاكم أو أن أخطئ.", "Mainly work and social relationships. I'm afraid of being judged or making a mistake."),
            ("psychologue", "La peur du jugement est très courante. Avez-vous déjà essayé des exercices de respiration pour calmer cette tension ?", "خوف الحكم عليه شائع جداً. هل جربت تمارين التنفس لتهدئة هذا التوتر؟", "Fear of judgment is very common. Have you tried breathing exercises to calm this tension?"),
            ("patient", "Non, je n'ai jamais essayé. Je ne sais pas par où commencer.", "لا، لم أحاول أبداً. لا أعرف من أين أبدأ.", "No, I've never tried. I don't know where to start."),
            ("psychologue", "Nous pouvons commencer par un exercice simple ensemble. Inspirez lentement par le nez pendant 4 secondes, puis expirez par la bouche.", "يمكننا البدء بتمرين بسيط معًا. اشترك ببطء من الأنف لمدة 4 ثوانٍ، ثم ازفر من الفم.", "We can start with a simple exercise together. Inhale slowly through the nose for 4 seconds, then exhale through the mouth."),
            ("patient", "D'accord, je vais essayer. Cela me semble un peu étrange mais je suis prêt à tester.", "حسنًا، سأحاول. يبدو لي الأمر غريباً بعض الشيء لكنني على استعداد لتجربته.", "Okay, I'll try. It seems a bit strange but I'm willing to test it."),
            ("psychologue", "C'est normal d'hésiter au début. L'important est d'avancer pas à pas, sans se juger.", "من الطبيعي التردد في البداية. الأهم هو التقدم خطوة بخطوة، دون الحكم على نفسك.", "It's normal to hesitate at first. The important thing is to move forward step by step, without judging yourself."),
            ("patient", "Merci pour votre patience. Je me sens un peu moins seul avec tout cela.", "شكراً على صبرك. أشعر ببعض الوحدة أقل مع كل هذا.", "Thank you for your patience. I feel a little less alone with all of this."),
            ("psychologue", "Je suis là pour vous accompagner. Nous pouvons reprendre cela à notre prochaine séance.", "أنا هنا لمرافقتك. يمكننا استئناف هذا في جلستنا القادمة.", "I am here to accompany you. We can resume this at our next session."),
            ("patient", "Oui, je pense que cela pourrait m'aider. À bientôt.", "نعم، أعتقد أن هذا يمكن أن يساعدني. إلى اللقاء.", "Yes, I think that could help me. See you soon."),
            ("psychologue", "À bientôt. Prenez soin de vous d'ici là.", "إلى اللقاء. اعتني بنفسك حتى ذلك الحين.", "See you soon. Take care of yourself until then."),
        ],
    },
    {
        "id": 2,
        "theme": "Dépression légère",
        "keywords_fr": ["dépression", "tristesse", "espoir", "fatigue"],
        "messages": [
            ("patient", "Je ressens une tristesse persistante depuis plusieurs semaines, sans raison précise.", "أشعر بحزن مستمر منذ عدة أسابيع، دون سبب محدد.", "I feel a persistent sadness for several weeks, without a specific reason."),
            ("psychologue", "Bonjour. Je vous écoute. Cette tristesse s'accompagne-t-elle d'une perte d'intérêt pour vos activités habituelles ?", "أهلاً بك. أنا أستمع إليك. هل يصاحب هذا الحزن فقدان interesse في أنشطتك المعتادة؟", "Hello. I'm listening. Is this sadness accompanied by a loss of interest in your usual activities?"),
            ("patient", "Oui, je n'ai plus envie de rien. Même les choses que j'aimais avant ne me procurent plus de plaisir.", "نعم، لا أرغب في أي شيء. حتى الأشياء التي كنت أحبها سابقًا لا تمنحني متعة بعد الآن.", "Yes, I don't feel like doing anything. Even things I used to enjoy no longer bring me pleasure."),
            ("psychologue", "C'est un symptôme fréquent de la dépression. Comment décririez-vous votre niveau d'énergie en ce moment ?", "هذا عرض متكرر للاكتئاب. كيف تصف مستوى طاقتك في الوقت الحالي؟", "This is a frequent symptom of depression. How would you describe your energy level right now?"),
            ("patient", "Très faible. Je me réveille épuisé et je traverse la journée comme un automate.", "منخفض جداً. أستيقظ منهكاً وأجتاز النهار كآلة.", "Very low. I wake up exhausted and get through the day like an automaton."),
            ("psychologue", "Je comprends. Avez-vous des pensées noires ou des idées sombres qui vous traversent l'esprit ?", "أفهم. هل لديك أفكار سلبية أو أفكار مخيفة تمر بذهنك؟", "I understand. Do you have dark or gloomy thoughts that cross your mind?"),
            ("patient", "Parfois je pense que je ne sers à rien, mais je n'oserais jamais passer à l'acte.", "أحيانًا أعتقد أنني لا أستحق شيئًا، لكنني لن أجرؤ أبدًا على التنفيذ.", "Sometimes I think I'm good for nothing, but I would never dare to act on it."),
            ("psychologue", "Il est important d'en parler. Ces pensées ne définissent pas qui vous êtes. Avez-vous un proche avec qui vous pouvez en parler ?", "من المهم التحدث عن ذلك. هذه الأفكار لا تحدد من أنت. هل لديك شخص مقرب يمكنك التحدث معه؟", "It's important to talk about it. These thoughts do not define who you are. Do you have a close person you can talk to?"),
            ("patient", "Ma sœur est au courant, mais je ne veux pas l'inquiéter davantage.", "أختي على علم، لكنني لا أريد أن أقلقها أكثر.", "My sister knows, but I don't want to worry her further."),
            ("psychologue", "C'est compréhensible. Peut-être pourriez-vous lui demander simplement de passer du temps avec vous, sans entrer dans les détails.", "هذا مفهوم. ربما يمكنك طلب منها فقط قضاء وقت معك، دون الدخول في التفاصيل.", "That's understandable. Maybe you could simply ask her to spend time with you, without going into details."),
            ("patient", "C'est une bonne idée. Je vais essayer de l'appeler ce week-end.", "فكرة جيدة. سأحاول الاتصال بها هذا الأسبوع.", "That's a good idea. I'll try to call her this weekend."),
            ("psychologue", "Excellent. Les petits pas comptent beaucoup. Nous reviendrons sur cela prochainement.", "ممتاز. الخطوات الصغيرة تهم كثيراً. سنعود إلى ذلك قريباً.", "Excellent. Small steps count a lot. We will come back to this soon."),
            ("patient", "Merci. Je me sens déjà un peu plus léger après cette conversation.", "شكراً. أشعر بالفعل بأنني أخف قليلاً بعد هذه المحادثة.", "Thank you. I already feel a little lighter after this conversation."),
            ("psychologue", "C'est un bon signe. Prenez soin de vous d'ici notre prochain échange.", "هذه علامة جيدة. اعتني بنفسك حتى تبادلنا القادم.", "That's a good sign. Take care of yourself until our next exchange."),
        ],
    },
    {
        "id": 3,
        "theme": "Stress professionnel / burn-out",
        "keywords_fr": ["burn-out", "travail", "épuisement", "surcharge"],
        "messages": [
            ("patient", "Je suis épuisé par mon travail. Les journées s'enchaînent et je n'ai plus de temps pour moi.", "أنا منهك من عملي. الأيام تتتالي ولا أملك وقتًا لنفسي.", "I am exhausted by my work. Days follow one another and I no longer have time for myself."),
            ("psychologue", "Bonjour. Merci de votre confiance. Depuis quand cette épuisement s'est-il installé ?", "أهلاً بك. شكراً على ثقتك. منذ متى استقر هذا الإرهاق؟", "Hello. Thank you for your trust. Since when has this exhaustion set in?"),
            ("patient", "Depuis environ un an, depuis ma promotion. Les responsabilités ont doublé sans augmentation d'équipe.", "منذ حوالي عام، منذ ترقتي. تضاعفت المسؤوليات دون زيادة في الفريق.", "For about a year, since my promotion. Responsibilities doubled without team increase."),
            ("psychologue", "Une promotion sans ressources supplémentaires est très difficile à gérer. Comment se passent vos nuits ?", "ترقية دون موارد إضافية صعبة جداً في الإدارة. كيف تمر لياليك؟", "A promotion without additional resources is very difficult to manage. How are your nights?"),
            ("patient", "Je me réveille souvent la nuit en pensant aux dossiers en retard. Je n'arrive plus à déconnecter.", "أستيقظ كثيرًا في الليل أفكر في الملفات المتأخرة. لا أستطيع الانفصال بعد الآن.", "I often wake up at night thinking about overdue files. I can no longer disconnect."),
            ("psychologue", "Le manque de déconnexion est un signe classique de burn-out. Avez-vous déjà envisagé de discuter de votre charge de travail avec votre responsable ?", "نقص الانفصال علامة كلاسيكية على الإرهاق المهني. هل فكرت يومًا في مناقشة حجم عملك مع مديرك؟", "Lack of disconnection is a classic sign of burn-out. Have you considered discussing your workload with your manager?"),
            ("patient", "J'ai peur que cela soit perçu comme un manque d'engagement ou de compétence.", "أخشى أن يُنظر إلى ذلك على أنه نقص في الالتزام أو الكفاءة.", "I'm afraid it will be perceived as a lack of commitment or competence."),
            ("psychologue", "C'est une crainte légitime. Pourtant, préserver votre santé est indispensable pour rester efficace sur le long terme.", "هذا خوف شرعي. ومع ذلك، الحفاظ على صحتك ضروري للبقاء فعالًا على المدى الطويل.", "That's a legitimate fear. However, preserving your health is essential to remain effective in the long term."),
            ("patient", "Vous avez raison. Je vais préparer une liste de mes tâches pour en parler avec lui.", "صعددت. سأعد قائمة بمهامي لأتحدث معه عنها.", "You are right. I will prepare a list of my tasks to discuss with him."),
            ("psychologue", "C'est une démarche constructive. N'oubliez pas d'inclure vos limites et vos besoins de récupération.", "هذه خطوة بناءة. لا تنس إدراج حدودك واحتياجاتك للتعافي.", "That's a constructive approach. Don't forget to include your limits and recovery needs."),
            ("patient", "D'accord, je note cela. Merci pour vos conseils.", "حسنًا، سأدونه. شكراً على نصائحك.", "Okay, I'll note that. Thank you for your advice."),
            ("psychologue", "Je vous en prie. Nous ferons le point ensemble lors de notre prochaine séance.", "على الرحب والسعة. سنقوم بالتقييم معًا في جلستنا القادمة.", "You're welcome. We will review together at our next session."),
            ("patient", "Je me sens déjà un peu moins écrasé par tout cela.", "أشعر بالفعل بأنني أقل سحقًا بكل هذا.", "I already feel a little less crushed by all of this."),
            ("psychologue", "C'est un progrès. Continuez à avancer à votre rythme.", "هذا تقدم. استمر في التقدم بوتيرتك الخاصة.", "That's progress. Continue moving at your own pace."),
        ],
    },
    {
        "id": 4,
        "theme": "Insomnie",
        "keywords_fr": ["insomnie", "sommeil", "nuit", "fatigue"],
        "messages": [
            ("patient", "Je n'arrive pas à dormir depuis des semaines. Je tourne dans mon lit pendant des heures.", "لا أستطيع النوم منذ أسابيع. أتقلب في سريري لساعات.", "I can't sleep for weeks. I toss in bed for hours."),
            ("psychologue", "Bonjour. Je vous écoute. Avez-vous des pensées qui tournent en boucle lorsque vous essayez de vous endormir ?", "أهلاً بك. أنا أستمع إليك. هل لديك أفكار تدور في حلقة عندما تحاول النوم؟", "Hello. I'm listening. Do you have thoughts that loop when you try to fall asleep?"),
            ("patient", "Oui, je repasse toute ma journée et je m'inquiète pour demain.", "نعم، أعيد يومي بأكمله وأقلق بشأن الغد.", "Yes, I go over my whole day and worry about tomorrow."),
            ("psychologue", "C'est un cercle vicieux : moins on dort, plus on s'inquiète. Avez-vous des rituels avant le coucher ?", "هذا حلقة مفرغة: كلما ن睡 weniger، كلما زادت القلق. هل لديك طقوس قبل النوم؟", "It's a vicious cycle: the less one sleeps, the more one worries. Do you have rituals before bedtime?"),
            ("patient", "Non, je vais me coucher quand je suis épuisé, souvent très tard.", "لا، أنام عندما أكون منهكًا، غالبًا في وقت متأخر.", "No, I go to bed when I'm exhausted, often very late."),
            ("psychologue", "Établir une heure de coucher régulière peut aider votre corps à se préparer au sommeil. Voulez-vous essayer de vous coucher à la même heure chaque soir ?", "تحديد وقت نوم منتظم يمكن أن يساعد جسمك على الاستعداد للنوم. هل تريد تجربة النوم في نفس الوقت كل ليلة؟", "Establishing a regular bedtime can help your body prepare for sleep. Would you like to try going to bed at the same time every night?"),
            ("patient", "Je peux essayer, mais j'ai peur de ne pas pouvoir m'endormir et de tourner encore plus longtemps.", "يمكنني المحاولة، لكن أخشى أن لا أستطيع النوم وأقلب لفترة أطول.", "I can try, but I'm afraid I won't be able to fall asleep and toss even longer."),
            ("psychologue", "C'est compréhensible. Si vous ne vous endormez pas après 20 minutes, levez-vous et faites une activité calme jusqu'à ce que le sommeil vienne.", "هذا مفهوم. إذا لم تنام بعد 20 دقيقة، قم وحدّث بنشاط هادئ حتى يأتي النوم.", "That's understandable. If you don't fall asleep after 20 minutes, get up and do a calm activity until sleep comes."),
            ("patient", "D'accord, je vais essayer cette approche cette nuit.", "حسنًا، سأجرب هذا النهج الليلة.", "Okay, I'll try this approach tonight."),
            ("psychologue", "Bien. Évitez aussi les écrans au moins une heure avant le coucher.", "جيد. تجنب الشاشات قبل ساعة على الأقل من النوم.", "Good. Also avoid screens at least one hour before bedtime."),
            ("patient", "C'est difficile car je travaille sur ordinateur jusque tard.", "هذا صعب لأنني أعمل على الكمبيوتر حتى وقت متأخر.", "It's difficult because I work on computer until late."),
            ("psychologue", "Essayez de vous déconnecter 30 minutes plus tôt chaque soir, progressivement.", "حاول قطع الاتصال قبل 30 دقيقة كل ليلة، تدريجياً.", "Try to disconnect 30 minutes earlier each evening, gradually."),
            ("patient", "Je vais essayer. Merci pour ces conseils concrets.", "سأحاول. شكراً على هذه النصائح الملموسة.", "I will try. Thank you for these concrete tips."),
            ("psychologue", "Je vous en prie. Nous ferons le point sur votre sommeil la prochaine fois.", "على الرحب والسعة. سنقيم نومك في المرة القادمة.", "You're welcome. We will review your sleep next time."),
        ],
    },
    {
        "id": 5,
        "theme": "Deuil d'un proche",
        "keywords_fr": ["deuil", "perte", "tristesse", "manque"],
        "messages": [
            ("patient", "J'ai perdu ma mère il y a trois mois et je n'arrive toujours pas à accepter son absence.", "فقدت والدتي منذ ثلاثة أشهر ولا أستطيع حتى الآن تقبل غيابها.", "I lost my mother three months ago and I still can't accept her absence."),
            ("psychologue", "Bonjour. Je suis de tout cœur avec vous dans cette épreuve. Parlez-moi d'elle, si vous le souhaitez.", "أهلاً بك. أنا مع كل قلبي معك في هذه المحنة.حدثني عنها، إذا رغبت في ذلك.", "Hello. I am with all my heart with you in this ordeal. Tell me about her, if you wish."),
            ("patient", "Elle était tout pour moi. Sa présence me manquait à chaque instant.", "كانت كل شيء بالنسبة لي. افتقد حضورها في كل لحظة.", "She was everything to me. I missed her presence at every moment."),
            ("psychologue", "Le lien avec une mère est unique. Quel souvenir vous revient le plus souvent à l'esprit ?", "الارتباط بالأم فريد. أي ذكرى تعود إلى ذهنك معظم الوقت؟", "The bond with a mother is unique. Which memory comes back to your mind most often?"),
            ("patient", "Ses rires quand nous cuisinions ensemble le dimanche. C'était nos moments à nous.", "ضحكاتها عندما نطبخ معًا يوم الأحد. كانت لحظاتنا الخاصة.", "Her laughs when we cooked together on Sunday. Those were our moments."),
            ("psychologue", "De beaux souvenirs. Il est normal de ressentir un vide immense. Acceptez-vous d'accueillir cette tristesse sans la combattre ?", "ذكريات جميلة. من الطبيعي أن تشعر بفقدان هائل. هل تقبل باستقبال هذا الحزن دون محاربته؟", "Beautiful memories. It is normal to feel an immense void. Are you willing to welcome this sadness without fighting it?"),
            ("patient", "J'essaie, mais certains jours c'est très dur. Je fonds en larmes sans prévenir.", "أحاول، لكن بعض الأيام يكون الأمر صعباً جداً. أنهار في البكاء دون سابق إنذار.", "I try, but some days it's very hard. I break into tears without warning."),
            ("psychologue", "Les émotions viennent par vagues. Laissez-les passer sans vous juger. Cela fait partie du cheminement.", "المشاعر تأتي على شكل موجات. دعها تمر دون حكم على نفسك. هذا جزء من الرحلة.", "Emotions come in waves. Let them pass without judging yourself. This is part of the journey."),
            ("patient", "Merci de me dire cela. Je me sens moins coupable d'être triste.", "شكراً على قول هذا لي. أشعر بأنني أقل ذنبًا لكوني حزينًا.", "Thank you for telling me that. I feel less guilty about being sad."),
            ("psychologue", "Il n'y a pas de bonne ou mauvaise façon de faire son deuil. Chacun avance à son rythme.", "لا توجد طريقة صحيحة أو خاطئة للحداد. كل شخص يتقدم بوتيرته الخاصة.", "There is no right or wrong way to grieve. Each person moves at their own pace."),
            ("patient", "Je vais essayer d'être plus doux avec moi-même.", "سأحاول أن أكون ألطف مع نفسي.", "I will try to be gentler with myself."),
            ("psychologue", "C'est une belle intention. Nous continuerons à explorer cela ensemble.", "هذه نية جميلة. سنواصل استكشاف ذلك معًا.", "That's a beautiful intention. We will continue to explore this together."),
            ("patient", "Oui, merci. Votre présence m'aide beaucoup.", "نعم، شكراً. وجودك يساعدني كثيرًا.", "Yes, thank you. Your presence helps me a lot."),
            ("psychologue", "Je suis là pour vous. Prenez soin de vous d'ici notre prochaine rencontre.", "أنا هنا من أجلك. اعتني بنفسك حتى لقاءنا القادم.", "I am here for you. Take care of yourself until our next meeting."),
        ],
    },
    {
        "id": 6,
        "theme": "Problèmes de couple / relation",
        "keywords_fr": ["couple", "conflit", "communication", "relation"],
        "messages": [
            ("patient", "Je traverse une période difficile avec mon conjoint. Nous nous disputons souvent pour des détails.", "أمر بفترة صعبة مع شريكي. نتشاجر كثيرًا بشأن تفاصيل بسيطة.", "I am going through a difficult period with my partner. We often argue about details."),
            ("psychologue", "Bonjour. Je vous écoute. Quels sont les sujets qui reviennent le plus souvent dans vos disputes ?", "أهلاً بك. أنا أستمع إليك. ما هي الموضوعات التي تعود أكثر في مشاجراتكم؟", "Hello. I'm listening. Which topics come up most often in your arguments?"),
            ("patient", "Principalement les tâches ménagères et le manque de temps passé ensemble.", "بشكل رئيسي الأعمال المنزلية ونقص الوقت الذي نقضيه معًا.", "Mainly household chores and lack of time spent together."),
            ("psychologue", "Le quotidien peut éroder la relation si l'on n'y prend pas garde. Comment communiquez-vous lorsque la tension monte ?", "الحياة اليومية يمكن أن ت corroded العلاقة إذا لم ننتبه. كيف تتواصلون عندما يرتفع التوتر؟", "Daily life can erode the relationship if one is not careful. How do you communicate when tension rises?"),
            ("patient", "Mal, nous crions souvent et nous ne nous écoutons pas vraiment.", "سيئ، نصرخ غالبًا ولا نسمع بعضنا حقًا.", "Bad, we often shout and we don't really listen to each other."),
            ("psychologue", "La colère empêche l'écoute. Avez-vous essayé de faire une pause lorsque vous sentez la tension monter, avant de reprendre la conversation ?", "الغضب يمنع الاستماع. هل جربت أخذ استراحة عندما تشعر أن التوتر يرتفع، قبل استئناف الحديث؟", "Anger prevents listening. Have you tried taking a break when you feel tension rising, before resuming the conversation?"),
            ("patient", "Non, on continue jusqu'à ce que l'un de nous parte en claquant la porte.", "لا، نستمر حتى يخرج أحدهم وهو يطيع الباب.", "No, we continue until one of us leaves slamming the door."),
            ("psychologue", "Cette pause pourrait vous aider à calmer le jeu et à exprimer vos besoins sans agressivité.", "هذه الاستراحة يمكن أن تساعدكم في تهدئة الأمور والتعبير عن احتياجاتكم دون عدوانية.", "This break could help you calm things down and express your needs without aggression."),
            ("patient", "Je vais essayer de proposer cela à mon conjoint lors de notre prochain calme.", "سأحاول اقتراح ذلك على شريكي خلال فترة هدوء قادمة.", "I will try to propose this to my partner during our next calm moment."),
            ("psychologue", "Excellente initiative. Vous pourriez aussi convenir d'un mot-clé pour signaler le besoin de pause.", "مبادرة ممتازة. يمكنك أيضًا الاتفاق على كلمة مفتاحية للإشارة إلى الحاجة للاستراحة.", "Excellent initiative. You could also agree on a keyword to signal the need for a break."),
            ("patient", "C'est une bonne idée. Merci pour ces pistes concrètes.", "فكرة جيدة. شكراً على هذه المسارات الملموسة.", "That's a good idea. Thank you for these concrete leads."),
            ("psychologue", "Je vous en prie. Nous ferons le point sur vos progrès relationnels bientôt.", "على الرحب والسعة. سنقيم تقدمك في العلاقات قريباً.", "You're welcome. We will review your relational progress soon."),
            ("patient", "Je me sens un peu plus optimiste pour notre couple.", "أشعر ببعض التفاؤل أكثر تجاه علاقتنا الزوجية.", "I feel a little more optimistic for our couple."),
            ("psychologue", "C'est encourageant. Continuez à cultiver le dialogue et la bienveillance mutuelle.", "هذا مشجع. استمر في تنمية الحوار واللطف المتبادل.", "That's encouraging. Continue cultivating dialogue and mutual kindness."),
        ],
    },
    {
        "id": 7,
        "theme": "Crise de panique",
        "keywords_fr": ["panique", "angoisse", "crise", "respiration"],
        "messages": [
            ("patient", "Je fais des crises de panique depuis quelques semaines. Mon cœur s'emballe et j'étouffe.", "أعاني من نوبات ذعر منذ أسابيع. يتسارع قلبي وأشعر بالاختناق.", "I have been having panic attacks for a few weeks. My heart races and I choke."),
            ("psychologue", "Bonjour. Je vous écoute. Ces crises surviennent-elles dans des situations précises ou de façon imprévisible ؟", "أهلاً بك. أنا أستمع إليك. هل تحدث هذه الأزمات في مواقف محددة أم بشكل غير متوقع؟", "Hello. I'm listening. Do these crises occur in specific situations or unpredictably?"),
            ("patient", "Principalement dans les lieux publics bondés, comme le métro ou les centres commerciaux.", "بشكل رئيسي في الأماكن العامة المزدحمة، مثل المترو أو مراكز التسوق.", "Mainly in crowded public places, like the subway or shopping malls."),
            ("psychologue", "L'agoraphobie accompagne souvent les crises de panique. Avez-vous déjà perdu connaissance durant une crise ?", "غالبًا ما يرافق رهاب الأماكن المفتوحة نوبات الذعر. هل أغمى عليك خلال نوبة؟", "Agoraphobia often accompanies panic attacks. Have you ever lost consciousness during an attack?"),
            ("patient", "Non, mais j'ai l'impression de mourir à chaque fois.", "لا، لكنني أشعر بالموت في كل مرة.", "No, but I feel like dying every time."),
            ("psychologue", "C'est une sensation très intense, mais ce n'est pas dangereux pour votre vie. Concentrez-vous sur votre respiration lorsque cela arrive.", "هذه sensación شديدة جداً، لكنها ليست خطرة على حياتك. ركز على تنفسك عندما يحدث ذلك.", "That's a very intense sensation, but it is not dangerous for your life. Focus on your breathing when it happens."),
            ("patient", "Je vais essayer de me concentrer sur ma respiration la prochaine fois.", "سأحاول التركيز على تنفسي في المرة القادمة.", "I will try to focus on my breathing next time."),
            ("psychologue", "La technique du carré (4-4-4-4) peut être utile : inspirez 4 secondes, retenez 4, expirez 4, retenez 4.", "تقنية المربع (4-4-4-4) قد تكون مفيدة: اشترك 4 ثوانٍ، احبس 4، ازفر 4، احبس 4.", "The square technique (4-4-4-4) can be useful: inhale 4 seconds, hold 4, exhale 4, hold 4."),
            ("patient", "D'accord, je vais essayer cet exercice quand je sens une crise arriver.", "حسنًا، سأجرب هذا التمرين عندما أشعر أن أزمة قادمة.", "Okay, I'll try this exercise when I feel a crisis coming."),
            ("psychologue", "Bien. Évitez aussi de fuir systématiquement les lieux qui déclenchent l'angoisse, cela l'entretiendrait.", "جيد. تجنب أيضًا الهروب بشكل منهجي من الأماكن التي تثير القلق، فهذا سيبقيه.", "Good. Also avoid systematically fleeing places that trigger anxiety, that would maintain it."),
            ("patient", "C'est difficile mais je comprends pourquoi c'est important.", "هذا صعب لكنني أفهم لماذا هو مهم.", "It's difficult but I understand why it's important."),
            ("psychologue", "Petit à petit, vous reprendrez confiance dans ces espaces.", "تدريجيًا، ستستعيد ثقتك في هذه الأماكن.", "Little by little, you will regain confidence in these spaces."),
            ("patient", "Merci pour votre soutien et vos explications claires.", "شكراً على دعمك وشرحك الوضوح.", "Thank you for your support and clear explanations."),
            ("psychologue", "Je vous en prie. Nous reviendrons sur vos progrès la prochaine fois.", "على الرحب والسعة. سنعود إلى تقدمك في المرة القادمة.", "You're welcome. We will come back to your progress next time."),
        ],
    },
    {
        "id": 8,
        "theme": "Estime de soi faible",
        "keywords_fr": ["estime de soi", "confiance", "valeur", "critique"],
        "messages": [
            ("patient", "J'ai du mal à m'apprécier. Je me critique constamment et je ne me sens jamais à la hauteur.", "أعاني في تقدير نفسي. أنتقد نفسي باستمرار ولا أشعر بأنني على قدر المسؤولية أبدًا.", "I have trouble appreciating myself. I constantly criticize myself and never feel up to it."),
            ("psychologue", "Bonjour. Merci de vous confier. Depuis quand ressentez-vous ce manque de confiance en vous ?", "أهلاً بك. شكرًا على ثقتك. منذ متى تشعر بنقص في ثقتك بنفسك؟", "Hello. Thank you for confiding in me. Since when do you feel this lack of self-confidence?"),
            ("patient", "Depuis longtemps, peut-être depuis l'adolescence. Mes parents avaient des attentes très élevées.", "منذ زمن طويل، ربما منذ المراهقة. كان لوالدي توقعات عالية جدًا.", "For a long time, maybe since adolescence. My parents had very high expectations."),
            ("psychologue", "Les attentes parentales élevées peuvent marquer durablement l'estime de soi. Que vous dites-vous lorsque vous faites une erreur ?", "التوقعات العالية من الوالدين يمكن أن تؤثر بشكل دائم على تقدير الذات. ماذا تقول لنفسك عندما ترتكب خطأ؟", "High parental expectations can mark self-esteem for a long time. What do you tell yourself when you make a mistake?"),
            ("patient", "Je me dis que je suis nul, que je vais échouer, que tout le monde va s'en rendre compte.", "أقول لنفسي إني فاشل، وأنني سأفشل، وأن الجميع سيلاحظ ذلك.", "I tell myself I'm useless, that I will fail, that everyone will notice."),
            ("psychologue", "Ce dialogue intérieur est très dur. Avez-vous remarqué si ces pensées sont basées sur des faits réels ou sur vos peurs ?", "هذا الحوار الداخلي شديد القساوة. هل لاحظت ما إذا كانت هذه الأفكار مبنية على حقائق فعلية أم على مخاوفك؟", "This inner dialogue is very harsh. Have you noticed whether these thoughts are based on real facts or your fears?"),
            ("patient", "Je pense que ce sont surtout mes peurs, mais elles semblent si réelles.", "أعتقد أنها في الغالب مخاوفي، لكنها تبدو حقيقية جدًا.", "I think they are mostly my fears, but they seem so real."),
            ("psychologue", "Nous pouvons travailler à remettre en question ces pensées automatiques. Souhaitez-vous essayer ensemble ?", "يمكننا العمل على التشكيك في هذه الأفكار التلقائية. هل ترغب في المحاولة معًا؟", "We can work on questioning these automatic thoughts. Would you like to try together?"),
            ("patient", "Oui, je veux apprendre à me parler avec plus de bienveillance.", "نعم، أريد أن أتعلم التحدث مع نفسي بلطف أكثر.", "Yes, I want to learn to speak to myself with more kindness."),
            ("psychologue", "Excellente décision. Commencez par identifier une pensée négative récurrente et remplacez-la par une phrase plus douce.", "قرارة ممتازة. ابدأ بتحديد فكرة سلبية متكررة واستبدلها بعبارة أكثر لطفًا.", "Excellent decision. Start by identifying a recurring negative thought and replace it with a softer phrase."),
            ("patient", "D'accord, je vais essayer de noter ces pensées dans un carnet.", "حسنًا، سأحاول تدوين هذه الأفكار في دفتر ملاحظاتي.", "Okay, I'll try to note these thoughts in a notebook."),
            ("psychologue", "C'est une bonne méthode. Nous examinerons ces notes ensemble à notre prochaine séance.", "هذه طريقة جيدة. سندون ملاحظاتنا معًا في جلستنا القادمة.", "That's a good method. We will review these notes together at our next session."),
            ("patient", "Je me sens déjà un peu plus léger après avoir mis des mots sur cela.", "أشعر بالفعل بأنني أخف قليلاً بعد وضع الكلمات على ذلك.", "I already feel a little lighter after putting words on this."),
            ("psychologue", "C'est un premier pas important. Continuez à vous observer avec curiosité et bienveillance.", "هذه خطوة أولى مهمة. استمر في مراقبة نفسك بفضول ولطف.", "That's an important first step. Continue to observe yourself with curiosity and kindness."),
        ],
    },
    {
        "id": 9,
        "theme": "TOC léger",
        "keywords_fr": ["TOC", "obsession", "compulsion", "vérification"],
        "messages": [
            ("patient", "Je vérifie plusieurs fois si j'ai bien fermé la porte et éteint le gaz avant de sortir.", "أتحقق عدة مرات مما إذا كنت قد أغلقت الباب وأطفأت الغاز قبل الخروج.", "I check several times if I properly closed the door and turned off the gas before leaving."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis combien de temps faites-vous ces vérifications répétées ?", "أهلاً بك. أنا أستمع إليك. منذ متى تقوم بهذه الفحوصات المتكررة؟", "Hello. I'm listening. Since when do you do these repeated checks?"),
            ("patient", "Depuis environ six mois. Cela me prend du temps et je suis souvent en retard.", "منذ حوالي ستة أشهر. يستغرق هذا وقتًا وأتأخر غالبًا.", "For about six months. This takes time and I am often late."),
            ("psychologue", "Le TOC peut s'installer progressivement. Ressentez-vous de l'anxiété si vous ne faites pas ces vérifications ?", "يمكن أن يتطور الوسواس القهري تدريجياً. هل تشعر بالقلق إذا لم تجري هذه الفحوصات؟", "OCD can set in gradually. Do you feel anxiety if you don't do these checks?"),
            ("patient", "Oui, j'ai peur qu'il arrive quelque chose de grave si je ne vérifie pas.", "نعم، أخشى أن يحدث شيء خطير إذا لم أتحقق.", "Yes, I'm afraid something serious will happen if I don't check."),
            ("psychologue", "C'est le mécanisme du TOC : la vérification soulage l'anxiété à court terme mais l'entretient à long terme.", "هذا آلية الوسواس القهري: التحقق يخفف القلق على المدى القصير لكنه يبقيه على المدى الطويل.", "That's the OCD mechanism: checking relieves anxiety short-term but maintains it long-term."),
            ("patient", "Je comprends, mais je ne sais pas comment m'en sortir seul.", "أفهم، لكنني لا أعرف كيف أرتاح وحدي.", "I understand, but I don't know how to get out of it alone."),
            ("psychologue", "Nous pouvons travailler ensemble sur l'exposition progressive : vérifier une fois, puis sortir sans revérifier.", "يمكننا العمل معًا على التعرض التدريجي: التحقق مرة واحدة، ثم الخروج دون إعادة التحقق.", "We can work together on gradual exposure: check once, then leave without re-checking."),
            ("patient", "Ça me fait peur, mais je suis prêt à essayer avec votre accompagnement.", "هذا يخيفني، لكنني على استعداد للمحاولة بمرافقتك.", "It scares me, but I'm ready to try with your accompaniment."),
            ("psychologue", "C'est courageux. Commencez par une vérification unique pour une porte peu importante, puis observez votre anxiété.", "هذا شجاع. ابدأ بالتحقق مرة واحدة لباب غير مهم، ثم راقب قلقك.", "That's courageous. Start with a single check for a low-importance door, then observe your anxiety."),
            ("patient", "D'accord, je vais essayer ce week-end chez moi.", "حسنًا، سأجرب هذا الأسبوع في منزلي.", "Okay, I'll try this weekend at home."),
            ("psychologue", "Bien. Notez ce que vous ressentez avant et après, nous en parlerons la prochaine fois.", "جيد. دوّن ما تشعر به قبل وبعد، وسنتحدث عن ذلك في المرة القادمة.", "Good. Note what you feel before and after, we will talk about it next time."),
            ("patient", "Merci pour votre aide et votre patience.", "شكراً على مساعدتك وصبرك.", "Thank you for your help and patience."),
            ("psychologue", "Je vous en prie. Vous avancez dans la bonne direction.", "على الرحب والسعة. أنت تتقدم في الاتجاه الصحيح.", "You're welcome. You are moving in the right direction."),
        ],
    },
    {
        "id": 10,
        "theme": "Phobie sociale",
        "keywords_fr": ["phobie sociale", "jugement", "isolement", "timidité"],
        "messages": [
            ("patient", "J'évite les réunions sociales parce que j'ai peur d'être jugé ou de dire quelque chose de maladroit.", "أتجنب المناسبات الاجتماعية لأنني أخشى أن أُحاكم أو أقول شيئًا غير لائق.", "I avoid social gatherings because I'm afraid of being judged or saying something awkward."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand évitez-vous ces situations ?", "أهلاً بك. أنا أستمع إليك. منذ متى تتجنب هذه المواقف؟", "Hello. I'm listening. Since when do you avoid these situations?"),
            ("patient", "Depuis plusieurs années, mais cela a empiré depuis mon changement de travail.", "منذ عدة سنوات، لكنها تفاقمت منذ تغيير عملي.", "For several years, but it has worsened since my job change."),
            ("psychologue", "Un changement d'environnement peut déclencher ou amplifier cette peur. Que redoutez-vous le plus dans ces moments-là ?", "تغيير البيئة يمكن أن يثير أو يزيد هذا الخوف. ما الذي تخشاه أكثر في هذه اللحظات؟", "A change of environment can trigger or amplify this fear. What do you fear most in those moments?"),
            ("patient", "Que les autres remarquent que je suis nerveux, que je rougis ou que je bafouille.", "أن يلاحظ الآخرون أنني متوتر، أو أنني أحمر أو أتعثر في الكلام.", "That others notice that I am nervous, that I blush or that I stutter."),
            ("psychologue", "La peur du regard des autres est centrale dans la phobie sociale. Avez-vous déjà essayé de vous exposer progressivement à ces situations ?", "الخوف من نظرات الآخرين مركزي في الرهاب الاجتماعي. هل جربت التعرض التدريجي لهذه المواقف؟", "Fear of others' gaze is central in social phobia. Have you tried gradually exposing yourself to these situations?"),
            ("patient", "Non, je les évite complètement pour ne pas ressentir cette angoisse.", "لا، أتجنبها تمامًا حتى لا أشعر بهذا القلق.", "No, I avoid them completely to not feel this anxiety."),
            ("psychologue", "L'évitement apporte un soulagement immédiat mais renforce la peur à long terme. Nous pourrions commencer par une toute petite exposition, comme saluer un voisin.", "التجنب يوفر ارتياحًا فوريًا لكنه يعزز الخوف على المدى الطويل. يمكننا البدء بتعرض صغير جدًا، مثل تحية جار.", "Avoidance brings immediate relief but reinforces fear long-term. We could start with a very small exposure, like greeting a neighbor."),
            ("patient", "Je peux essayer de faire cela cette semaine.", "يمكنني محاولة فعل ذلك هذا الأسبوع.", "I can try to do that this week."),
            ("psychologue", "Bien. Notez votre niveau d'anxiété avant et après, nous analyserons cela ensemble.", "جيد. دوّن مستوى قلقك قبل وبعد، وسنحلل ذلك معًا.", "Good. Note your anxiety level before and after, we will analyze that together."),
            ("patient", "D'accord, je vais tenir un petit journal de mes progrès.", "حسنًا، سأحتفظ بسجل صغير لتقدمي.", "Okay, I will keep a small journal of my progress."),
            ("psychologue", "C'est une excellente méthode pour prendre conscience de vos avancées.", "هذه طريقة ممتازة لتكون واعيًا بتقدمك.", "That's an excellent method to become aware of your progress."),
            ("patient", "Merci pour votre encouragement et vos conseils.", "شكراً على تشجيعك ونصائحك.", "Thank you for your encouragement and advice."),
            ("psychologue", "Je vous en prie. Chaque petit pas compte vers plus de liberté sociale.", "على الرحب والسعة. كل خطوة صغيرة تهم نحو حرية اجتماعية أكبر.", "You're welcome. Every small step counts towards more social freedom."),
        ],
    },
    {
        "id": 11,
        "theme": "Addiction (écrans / jeu)",
        "keywords_fr": ["addiction", "écrans", "jeu", "contrôle"],
        "messages": [
            ("patient", "Je passe trop de temps sur mon téléphone et aux jeux en ligne. Je perds le contrôle du temps.", "أقضي وقتًا طويلاً على هاتفي وألعاب الإنترنت. أفقد السيطرة على الوقت.", "I spend too much time on my phone and online games. I lose control of time."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand ce comportement est-il devenu problématique pour vous ?", "أهلاً بك. أنا أستمع إليك. منذ متى أصبح هذا السلوك مشكلة بالنسبة لك؟", "Hello. I'm listening. Since when has this behavior become problematic for you?"),
            ("patient", "Depuis environ un an. Je néglige mes responsabilités et mes relations à cause de cela.", "منذ حوالي عام. أهمل مسؤولياتي وعلاقاتي بسبب ذلك.", "For about a year. I neglect my responsibilities and relationships because of this."),
            ("psychologue", "L'addiction aux écrans peut isoler progressivement. Ressentez-vous une envie irrépressible de vous connecter lorsque vous essayez d'arrêter ?", "يمكن أن تعزل الإدمان على الشاشات تدريجياً. هل تشعر برغبة لا تقاوم في الاتصال عندما تحاول التوقف؟", "Screen addiction can isolate gradually. Do you feel an irresistible urge to connect when you try to stop?"),
            ("patient", "Oui, je deviens irritable et je pense constamment à mon prochain écran.", "نعم، أصبح سريع الانفعال وأفكر باستمرار في شاشتي التالية.", "Yes, I become irritable and constantly think about my next screen."),
            ("psychologue", "C'est un signe de dépendance. Nous pouvons travailler à réduire progressivement le temps d'écran avec des plages horaires définies.", "هذا علامة على الاعتماد. يمكننا العمل على تقليل وقت الشاشة تدريجياً مع فترات زمنية محددة.", "That's a sign of dependence. We can work on gradually reducing screen time with defined time slots."),
            ("patient", "Je suis prêt à essayer, mais j'ai peur de l'ennui sans mes écrans.", "أنا على استعداد للمحاولة، لكنني أخشى من الملل دون شاشاتي.", "I am ready to try, but I'm afraid of boredom without my screens."),
            ("psychologue", "L'ennui peut être remplacé par d'autres activités : lecture, sport, sorties avec des amis.", "يمكن استبدال الملل بأنشطة أخرى: القراءة، الرياضة، النزهات مع الأصدقاء.", "Boredom can be replaced by other activities: reading, sports, outings with friends."),
            ("patient", "J'aimerais reprendre le sport, mais je n'ai plus d'énergie le soir.", "أود استئناف الرياضة، لكنني لا أملك طاقة في المساء.", "I would like to resume sports, but I no longer have energy in the evening."),
            ("psychologue", "Commencez par une courte activité, même 15 minutes, pour réactiver votre énergie.", "ابدأ بنشاط قصير، حتى 15 دقيقة، لإعادة تنشيط طاقتك.", "Start with a short activity, even 15 minutes, to reactivate your energy."),
            ("patient", "D'accord, je vais essayer une marche courte ce week-end.", "حسنًا، سأجرب مشيًا قصيرًا هذا الأسبوع.", "Okay, I'll try a short walk this weekend."),
            ("psychologue", "Excellente idée. Nous ferons le point sur vos progrès la prochaine fois.", "فكرة ممتازة. سنقيم تقدمك في المرة القادمة.", "Excellent idea. We will review your progress next time."),
            ("patient", "Merci pour votre aide et votre compréhension.", "شكراً على مساعدتك وتفهمك.", "Thank you for your help and understanding."),
            ("psychologue", "Je vous en prie. Vous reprenez le contrôle pas à pas.", "على الرحب والسعة. أنت تستعيد السيطرة خطوة بخطوة.", "You're welcome. You are regaining control step by step."),
        ],
    },
    {
        "id": 12,
        "theme": "Trouble alimentaire",
        "keywords_fr": ["alimentation", "corps", "image de soi", "contrôle"],
        "messages": [
            ("patient", "J'ai du mal avec mon alimentation. Je contrôle ce que je mange de manière obsessionnelle.", "أعاني من طعامي. أت kontrol ما أأكله بطريقة هوسية.", "I have trouble with my eating. I control what I eat obsessively."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand ce contrôle alimentaire est-il présent ?", "أهلاً بك. أنا أستمع إليك. منذ متى يوجد هذا التحكم في الطعام؟", "Hello. I'm listening. Since when has this food control been present?"),
            ("patient", "Depuis environ huit mois. Je me pèse tous les jours et je me juge selon le chiffre.", "منذ حوالي ثمانية أشهر. أزن نفسي كل يوم وأحكّم على نفسي حسب الرقم.", "For about eight months. I weigh myself every day and judge myself according to the number."),
            ("psychologue", "Le lien entre le poids et l'estime de soi peut devenir malsain. Comment vous sentez-vous après un repas ?", "الارتباط بين الوزن وتقدير الذات يمكن أن يصبح غير صحي. كيف تشعر بعد وجبة طعام؟", "The link between weight and self-esteem can become unhealthy. How do you feel after a meal?"),
            ("patient", "Souvent coupable si j'ai mangé quelque chose de 'interdit', et anxieux avant de manger.", "غالبًا مذنب إذا أكلت شيئًا 'ممنوعًا'، وقلقًا قبل الأكل.", "Often guilty if I ate something 'forbidden', and anxious before eating."),
            ("psychologue", "Cette culpabilité est un signal important. Avez-vous déjà pensé à consulter un nutritionniste en parallèle de notre suivi ?", "هذا الشعور بالذنب إشارة مهمة. هل فكرت يومًا في استشارة أخصائي تغذية بالتوازي مع متابعتنا؟", "This guilt is an important signal. Have you thought about consulting a nutritionist in parallel with our follow-up?"),
            ("patient", "Non, je n'y avais pas pensé. Cela pourrait m'aider à avoir une approche plus saine.", "لا، لم أفكر في ذلك. يمكن أن يساعدني في اتباع نهج أكثر صحة.", "No, I hadn't thought about it. This could help me have a healthier approach."),
            ("psychologue", "C'est une piste intéressante. Nous pouvons aussi travailler sur l'acceptation de votre corps tel qu'il est.", "هذا مسار مثير للاهتمام. يمكننا أيضًا العمل على قبول جسمك كما هو.", "That's an interesting track. We can also work on accepting your body as it is."),
            ("patient", "Je veux apprendre à m'accepter, mais c'est difficile après tant d'années de critique.", "أريد أن أتعلم قبول نفسي، لكنه صعب بعد سنوات عديدة من الانتقاد.", "I want to learn to accept myself, but it's difficult after so many years of criticism."),
            ("psychologue", "C'est un chemin qui demande du temps et de la patience. Nous avancerons à votre rythme.", "هذا طريق يحتاج وقتًا وصبرًا. سنتقدم بوتيرتك الخاصة.", "It's a path that takes time and patience. We will move at your pace."),
            ("patient", "Merci pour votre soutien sans jugement.", "شكراً على دعمك بدون حكم.", "Thank you for your non-judgmental support."),
            ("psychologue", "Je vous en prie. Chaque repas peut être une occasion de pratiquer la bienveillance envers vous-même.", "على الرحب والسعة. كل وجبة يمكن أن تكون فرصة لممارسة اللطف تجاه نفسك.", "You're welcome. Every meal can be an opportunity to practice kindness towards yourself."),
        ],
    },
    {
        "id": 13,
        "theme": "Stress post-traumatique",
        "keywords_fr": ["traumatisme", "flashback", "peur", "sécurité"],
        "messages": [
            ("patient", "J'ai vécu un accident il y a un an et depuis je fais des cauchemars et des flashbacks.", "عانيت من حادث قبل عام ومنذ ذلك الحين أعاني من كوابيس واسترجاعات.", "I experienced an accident a year ago and since then I have nightmares and flashbacks."),
            ("psychologue", "Bonjour. Je vous écoute. Ces flashbacks sont-ils déclenchés par des situations précises ?", "أهلاً بك. أنا أستمع إليك. هل تُطلق هذه الاسترجاعات مواقف محددة؟", "Hello. I'm listening. Are these flashbacks triggered by specific situations?"),
            ("patient", "Oui, surtout les bruits forts qui ressemblent à l'accident, comme le freinage d'une voiture.", "نعم، خاصة الأصوات العالية التي تشبه الحادث، مثل فرملة سيارة.", "Yes, especially loud noises that resemble the accident, like a car braking."),
            ("psychologue", "C'est typique du stress post-traumatique. Le cerveau reste en état d'alerte. Ressentez-vous de l'hypervigilance au quotidien ?", "هذا típico من الإجهاد ما بعد الصدمة. يبقى الدماغ في حالة تأهب. هل تشعر بتوتر مفرط في الحياة اليومية؟", "That's typical of post-traumatic stress. The brain remains on alert. Do you feel hypervigilance in daily life?"),
            ("patient", "Oui, je surveille constamment mon environnement et je suis facilement surpris.", "نعم، أراقب بيئتي باستمرار وأُفاجأ بسهولة.", "Yes, I constantly monitor my environment and am easily startled."),
            ("psychologue", "Nous pouvons travailler sur des techniques d'ancrage pour vous aider à revenir au présent lorsque cela arrive.", "يمكننا العمل على تقنيات الارتكاز لمساعدتك على العودة للحاضر عندما يحدث ذلك.", "We can work on grounding techniques to help you return to the present when this happens."),
            ("patient", "Je suis prêt à essayer n'importe quoi pour aller mieux.", "أنا على استعداد لتجربة أي شيء لأشعر بتحسن.", "I am ready to try anything to feel better."),
            ("psychologue", "La technique 5-4-3-2-1 peut aider : identifiez 5 choses que vous voyez, 4 que vous touchez, 3 que vous entendez, 2 que vous sentez, 1 que vous goûtez.", "تقنية 5-4-3-2-1 يمكن أن تساعد: حدد 5 أشياء تراها، 4 تلمسها، 3 تسمعها، 2 تشمها، 1 تتذوقها.", "The 5-4-3-2-1 technique can help: identify 5 things you see, 4 you touch, 3 you hear, 2 you smell, 1 you taste."),
            ("patient", "Je vais essayer cette technique la prochaine fois que je me sentirai envahi par un souvenir.", "سأجرب هذه التقنية في المرة القادمة التي أشعر فيها بأنني غارق في ذكرى.", "I will try this technique next time I feel overwhelmed by a memory."),
            ("psychologue", "Bien. Notez si cela vous aide à calmer l'intensité du flashback.", "جيد. دوّن إذا ما كان ذلك يساعدك في تهدئة شدة الاسترجاع.", "Good. Note if this helps you calm the intensity of the flashback."),
            ("patient", "D'accord, je vais tenir un registre de ces moments.", "حسنًا، سأحتفظ بسجل لهذه اللحظات.", "Okay, I will keep a record of these moments."),
            ("psychologue", "Nous en reparlerons ensemble à notre prochaine séance.", "سنتحدث عن ذلك معًا في جلستنا القادمة.", "We will talk about it together at our next session."),
            ("patient", "Merci pour votre écoute et votre bienveillance.", "شكراً على استماعك ولطفك.", "Thank you for your listening and kindness."),
            ("psychologue", "Je vous en prie. Vous n'êtes pas seul dans ce cheminement.", "على الرحب والسعة. أنت لست وحدك في هذا المسار.", "You're welcome. You are not alone in this journey."),
        ],
    },
    {
        "id": 14,
        "theme": "Solitude / isolement",
        "keywords_fr": ["solitude", "isolement", "liens", "connexion"],
        "messages": [
            ("patient", "Je me sens très seul depuis mon déménagement dans cette nouvelle ville.", "أشعر بالوحدة الشديدة منذ انتقالي إلى هذه المدينة الجديدة.", "I feel very alone since my move to this new city."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand habitez-vous dans cette ville ?", "أهلاً بك. أنا أستمع إليك. منذ متى تعيش في هذه المدينة؟", "Hello. I'm listening. Since when do you live in this city?"),
            ("patient", "Depuis quatre mois. Je connais peu de gens et je n'ai pas encore créé de liens.", "منذ أربعة أشهر. أعرف القليل من الأشخاص ولم أنشئ علاقات بعد.", "For four months. I know few people and haven't created bonds yet."),
            ("psychologue", "Changer de ville est un défi social important. Quelles activités aimeriez-vous faire pour rencontrer du monde ?", "تغيير المدينة هو تحدٍ اجتماعي مهم. ما هي الأنشطة التي تود ممارستها لمقابلة الناس؟", "Changing city is a major social challenge. What activities would you like to do to meet people?"),
            ("patient", "J'aimerais rejoindre un club de lecture ou faire du bénévolat، mais je n'ose pas franchir le pas.", "أرغب في الانضمام لنادي قراءة أو العمل التطوعي، لكنني لا أجرؤ على الخطوة.", "I would like to join a book club or do volunteering, but I don't dare to take the step."),
            ("psychologue", "C'est compréhensible. La peur du rejet peut freiner. Pourriez-vous commencer par visiter un événement une seule fois, sans engagement à long terme ؟", "هذا مفهوم. خوف الرفض يمكن أن يثبط. هل يمكنك حضور حدث مرة واحدة فقط، دون التزام طويل المدى؟", "That's understandable. Fear of rejection can hold back. Could you start by attending an event once, without long-term commitment?"),
            ("patient", "Oui, je pense que je peux essayer cela ce mois-ci.", "نعم، أعتقد أنه يمكنني المحاولة هذا الشهر.", "Yes, I think I can try that this month."),
            ("psychologue", "Bien. Même une courte interaction peut être un premier pas vers de nouvelles connexions.", "جيد. حتى تفاعل قصير يمكن أن يكون خطوة أولى نحو اتصالات جديدة.", "Good. Even a short interaction can be a first step towards new connections."),
            ("patient", "Je vais chercher des événements locaux cette semaine.", "سأبحث عن فعاليات محلية هذا الأسبوع.", "I will look for local events this week."),
            ("psychologue", "Excellente initiative. Nous ferons le point sur vos rencontres la prochaine fois.", "مبادرة ممتازة. سنقيم لقاءاتك في المرة القادمة.", "Excellent initiative. We will review your meetings next time."),
            ("patient", "Merci pour votre encouragement.", "شكراً على تشجيعك.", "Thank you for your encouragement."),
            ("psychologue", "Je vous en prie. Petit à petit, vous recréerez du lien social.", "على الرحب والسعة. تدريجيًا، ستعيد بناء الروابط الاجتماعية.", "You're welcome. Little by little, you will recreate social bonds."),
            ("patient", "Je me sens déjà un peu plus espoir pour l'avenir.", "أشعر بالفعل ببعض الأمل أكثر للمستقبل.", "I already feel a little more hope for the future."),
            ("psychologue", "C'est un bon signe. Continuez à avancer à votre rythme.", "هذه علامة جيدة. استمر في التقدم بوتيرتك الخاصة.", "That's a good sign. Continue moving at your own pace."),
        ],
    },
    {
        "id": 15,
        "theme": "Colère / gestion des émotions",
        "keywords_fr": ["colère", "émotions", "contrôle", "conflit"],
        "messages": [
            ("patient", "J'ai du mal à contrôler ma colère. Je m'emporte facilement et je regrette après.", "أعاني في السيطرة على غضبي. أستثير بسهولة وأندم بعد ذلك.", "I have trouble controlling my anger. I get angry easily and regret after."),
            ("psychologue", "Bonjour. Je vous écoute. Dans quelles situations cette colère surgit-elle le plus souvent ?", "أهلاً بك. أنا أستمع إليك. في أي المواقف يظهر هذا الغضب غالبًا؟", "Hello. I'm listening. In which situations does this anger arise most often?"),
            ("patient", "Principalement quand je me sens incompris ou quand les choses ne se passent pas comme prévu.", "بشكل رئيسي عندما أشعر بأنني غير مفهوم أو عندما لا تسير الأمور كما هو مخطط لها.", "Mainly when I feel misunderstood or when things don't go as planned."),
            ("psychologue", "La frustration face à l'imprévu est fréquente. Quelles sensations physiques ressentez-vous lorsque la colère monte ?", "الإحباط تجاه غير المتوقع متكرر. ما هي الإحساسات الجسدية التي تشعر بها عندما يرتفع الغضب؟", "Frustration towards the unexpected is frequent. What physical sensations do you feel when anger rises?"),
            ("patient", "Mon cœur bat vite, je sens la chaleur monter et je serre les poings.", "يدق قلبي بسرعة، أشعر بالحرارة وأبض على قبضتي.", "My heart beats fast, I feel heat rising and I clench my fists."),
            ("psychologue", "Ces signes précurseurs sont importants à repérer. Avez-vous déjà essayé de compter jusqu'à 10 avant de réagir ?", "هذه العلامات المبكرة مهمة لرصدها. هل جربت العد حتى 10 قبل التفاعل؟", "These warning signs are important to spot. Have you tried counting to 10 before reacting?"),
            ("patient", "Non, mais je suis prêt à essayer la prochaine fois.", "لا، لكنني على استعداد للمحاولة في المرة القادمة.", "No, but I'm ready to try next time."),
            ("psychologue", "Vous pouvez aussi essayer de vous éloigner quelques minutes de la situation pour vous calmer avant de revenir.", "يمكنك أيضًا محاولة الابتعاد بضع دقائق عن الموقف لتهدئة نفسك قبل العودة.", "You can also try to step away a few minutes from the situation to calm down before returning."),
            ("patient", "Je vais essayer ces deux techniques la prochaine fois que je serai en colère.", "سأجرب هاتين التقنيتين في المرة القادمة التي أغضب فيها.", "I will try these two techniques next time I am angry."),
            ("psychologue", "Bien. Notez ce qui a fonctionné et ce qui a été difficile, nous en parlerons ensemble.", "جيد. دوّن ما عمل وما كان صعبًا، وسنتحدث عنه معًا.", "Good. Note what worked and what was difficult, we will talk about it together."),
            ("patient", "D'accord, je tiendrai un petit carnet de mes émotions.", "حسنًا، سأحتفظ بدفتر صغير لمشاعري.", "Okay, I will keep a small notebook of my emotions."),
            ("psychologue", "C'est une bonne méthode pour prendre du recul sur vos réactions.", "هذه طريقة جيدة لأخذ مسافة على ردود فعلك.", "That's a good method to take distance from your reactions."),
            ("patient", "Merci pour vos conseils pratiques.", "شكراً على نصائحك العملية.", "Thank you for your practical advice."),
            ("psychologue", "Je vous en prie. La gestion de la colère s'apprend avec la pratique.", "على الرحب والسعة. إدارة الغضب تتعلم بالممارسة.", "You're welcome. Anger management is learned with practice."),
        ],
    },
    {
        "id": 16,
        "theme": "Transition de vie",
        "keywords_fr": ["changement", "transition", "adaptation", "nouveau départ"],
        "messages": [
            ("patient", "Je traverse une période de transition importante avec mon nouveau travail et mon déménagement.", "أمر بفترة انتقال مهمة مع عملي الجديد وانتقالي.", "I am going through an important transition period with my new job and my move."),
            ("psychologue", "Bonjour. Je vous écoute. Quels changements récents vivez-vous ?", "أهلاً بك. أنا أستمع إليك. ما هي التغييرات الأخيرة التي تعيشها؟", "Hello. I'm listening. What recent changes are you experiencing?"),
            ("patient", "Nouveau travail, nouvelle ville, nouveaux repères. Tout a changé en même temps.", "عمل جديد، مدينة جديدة، معالم جديدة. كل شيء تغير في نفس الوقت.", "New job, new city, new landmarks. Everything changed at the same time."),
            ("psychologue", "C'est beaucoup de changements à intégrer d'un coup. Comment vous sentez-vous face à tout cela ?", "هذا الكثير من التغييرات للاستيعاب مرة واحدة. كيف تشعر تجاه كل هذا؟", "That's a lot of changes to integrate at once. How do you feel facing all this?"),
            ("patient", "Excité mais aussi dépassé. Je ne sais pas par où commencer pour m'organiser.", "متحمس ولكن أيضًا منهار. لا أعرف من أين أبدأ لأنظم نفسي.", "Excited but also overwhelmed. I don't know where to start to organize myself."),
            ("psychologue", "Faire une liste des priorités peut vous aider à y voir plus clair. Quelles sont vos trois priorités cette semaine ؟", "إعداد قائمة بالأولويات يمكن أن يساعدك في الرؤية بوضوح. ما هي أولوياتك الثلاثة هذا الأسبوع؟", "Making a priority list can help you see more clearly. What are your three priorities this week?"),
            ("patient", "M'installer dans mon nouvel appartement, rencontrer mes collègues et trouver mes repères dans la ville.", "الت asent في شقتي الجديدة، مقابلة زملائي وإيجاد معالمي في المدينة.", "Settle in my new apartment, meet my colleagues and find my landmarks in the city."),
            ("psychologue", "Ce sont des objectifs concrets. Commencez par le plus accessible et avancez pas à pas.", "هذه أهداف ملموسة. ابدأ بالأسهل وتقدم خطوة بخطوة.", "These are concrete objectives. Start with the most accessible and move step by step."),
            ("patient", "Je vais commencer par déballer mes affaires et organiser mon espace.", "سأبدأ بفك أغراضي وتنظيم مساحتي.", "I will start by unpacking my things and organizing my space."),
            ("psychologue", "Bien. Créer un environnement familier vous aidera à vous sentir chez vous plus rapidement.", "جيد. إنشاء بيئة مألوفة سيساعدك على الشعور في منزلك بشكل أسرع.", "Good. Creating a familiar environment will help you feel at home more quickly."),
            ("patient", "Merci pour vos conseils, je me sens un peu moins dépassé.", "شكراً على نصائحك، أشعر بأنني أقل إرهاقًا.", "Thank you for your advice, I feel a little less overwhelmed."),
            ("psychologue", "Je vous en prie. Chaque petit progrès compte dans cette transition.", "على الرحب والسعة. كل تقدم صغير يهم في هذه الفترة الانتقالية.", "You're welcome. Every small progress counts in this transition."),
            ("patient", "Je me sens déjà un peu plus confiant pour les prochains jours.", "أشعر بالفعل ببعض الثقة أكثر للأيام القادمة.", "I already feel a little more confident for the coming days."),
            ("psychologue", "C'est encourageant. Continuez à avancer avec douceur envers vous-même.", "هذا مشجع. استمر في التقدم بلطف تجاه نفسك.", "That's encouraging. Continue moving forward with gentleness towards yourself."),
        ],
    },
    {
        "id": 17,
        "theme": "Anxiété de performance (examens)",
        "keywords_fr": ["examen", "performance", "stress", "préparation"],
        "messages": [
            ("patient", "Je passe des examens importants dans quelques semaines et je suis très anxieux.", "سوف أؤدي امتحانات مهمة بعد بضعة أسابيع وأنا قلق جدًا.", "I am taking important exams in a few weeks and I am very anxious."),
            ("psychologue", "Bonjour. Je vous écoute. Qu'est-ce qui vous angoisse le plus dans ces examens ?", "أهلاً بك. أنا أستمع إليك. ما الذي يثير قلقك أكثر في هذه الامتحانات؟", "Hello. I'm listening. What worries you most about these exams?"),
            ("patient", "J'ai peur d'échouer et de décevoir ma famille qui compte sur moi.", "أخشى الفشل وخيبة عائلتي التي تعتمد عليّ.", "I'm afraid of failing and disappointing my family who counts on me."),
            ("psychologue", "La pression familiale peut être lourde. Comment organisez-vous vos révisions actuellement ?", "الضغط العائلي يمكن أن يكون ثقيلاً. كيف تنظم مراجعاتك حالياً؟", "Family pressure can be heavy. How do you organize your revisions currently?"),
            ("patient", "J'étudie tard le soir et je saute parfois des repas pour gagner du temps.", "أدرس حتى وقت متأخر في الليل وأتجاهل بعض الوجبات أحيانًا لأوفر الوقت.", "I study late at night and sometimes skip meals to save time."),
            ("psychologue", "Sauter des repas et dormir peu réduit vos capacités cognitives. Avez-vous prévu des pauses régulières dans votre planning ?", "تخطي الوجبات والنوم القليل يقلل قدراتك الإدراكية. هل خصصت فترات استراحة منتظمة في خطتك؟", "Skipping meals and sleeping little reduces your cognitive abilities. Have you planned regular breaks in your schedule?"),
            ("patient", "Non, j'essaie d'étudier le plus possible sans m'arrêter.", "لا، أحاول الدراسة قدر الإمكان دون توقف.", "No, I try to study as much as possible without stopping."),
            ("psychologue", "C'est contre-productif. Le cerveau a besoin de repos pour mémoriser. Essayez la méthode Pomodoro : 25 minutes de travail, 5 minutes de pause.", "هذا غير منتج. الدماغ يحتاج לרاحة للتذكر. جرب تقنية بومودورو: 25 دقيقة عمل، 5 دقائق استراحة.", "That's counterproductive. The brain needs rest to memorize. Try the Pomodoro method: 25 minutes work, 5 minutes break."),
            ("patient", "Je vais essayer cette méthode pour mes prochaines révisions.", "سأجرب هذه الطريقة لمراجعاتي القادمة.", "I will try this method for my next revisions."),
            ("psychologue", "Bien. Et prévoyez une bonne nuit de sommeil avant chaque jour d'examen.", "جيد. واستعد ليلة نوم جيدة قبل كل يوم امتحان.", "Good. And plan a good night's sleep before each exam day."),
            ("patient", "D'accord, je vais essayer de me coucher plus tôt ces prochains jours.", "حسنًا، سأحاول النوم في وقت أبكر في الأيام القادمة.", "Okay, I will try to go to bed earlier in the coming days."),
            ("psychologue", "Excellent. Nous ferons le point sur votre préparation la prochaine fois.", "ممتاز. سنقيم استعداداتك في المرة القادمة.", "Excellent. We will review your preparation next time."),
            ("patient", "Merci pour vos conseils, je me sens déjà un peu moins stressé.", "شكراً على نصائحك، أشعر بأنني أقل توترًا بالفعل.", "Thank you for your advice, I already feel a little less stressed."),
            ("psychologue", "Je vous en prie. Vous avez toutes les capacités pour réussir, prenez soin de vous.", "على الرحب والسعة. لديك كل القدرات للنجاح، اعتني بنفسك.", "You're welcome. You have all the abilities to succeed, take care of yourself."),
        ],
    },
    {
        "id": 18,
        "theme": "Relations familiales conflictuelles",
        "keywords_fr": ["famille", "conflit", "parents", "communication"],
        "messages": [
            ("patient", "J'ai des conflits fréquents avec mes parents sur mes choix de vie.", "لدي صراعات متكررة مع والديّ بشأن خيارات حياتي.", "I have frequent conflicts with my parents about my life choices."),
            ("psychologue", "Bonjour. Je vous écoute. Quels sont les sujets de conflit principaux ?", "أهلاً بك. أنا أستمع إليك. ما هي الموضوعات الرئيسية للصراع؟", "Hello. I'm listening. What are the main conflict topics?"),
            ("patient", "Mon choix de carrière, ma vie amoureuse et la façon dont je veux vivre ma vie.", "اختياري المهني، حياتي العاطفية، وطريقة عيش حياتي.", "My career choice, my love life and the way I want to live my life."),
            ("psychologue", "Le conflit entre autonomie personnelle et attentes familiales est courant. Comment communiquez-vous avec eux actuellement ?", "الصراع بين الاستقلالية الشخصية وتوقعات العائلة شائع. كيف تتواصل معهم حالياً؟", "The conflict between personal autonomy and family expectations is common. How do you communicate with them currently?"),
            ("patient", "Mal, nous discutons souvent et personne n'écoute vraiment l'autre.", "سيئ، نناقش غالبًا ولا يستمع أحد للآخر حقًا.", "Bad, we often argue and no one really listens to the other."),
            ("psychologue", "L'écoute mutuelle est essentielle. Avez-vous déjà essayé d'exprimer vos sentiments en utilisant des phrases en 'je' plutôt qu'en 'tu' ?", "الاستماع المتبادل ضروري. هل جربت التعبير عن مشاعرك باستخدام جمل بـ 'أنا' بدلاً من 'أنت'؟", "Mutual listening is essential. Have you tried expressing your feelings using 'I' statements rather than 'you'?"),
            ("patient", "Non, je ne connais pas cette technique. Pouvez-vous m'expliquer ?", "لا، لا أعرف هذه التقنية. هل يمكنك شرحها لي؟", "No, I don't know this technique. Can you explain it to me?"),
            ("psychologue", "Au lieu de dire 'Tu ne comprends jamais', dites 'Je me sens incompris lorsque nous parlons de cela'. Cela réduit la défensive.", "بدلاً من قول 'أنت لا تفهم أبدًا'، قل 'أشعر بأنني غير مفهوم عندما نتحدث عن ذلك'. هذا يقلل الدفاعية.", "Instead of saying 'You never understand', say 'I feel misunderstood when we talk about this'. This reduces defensiveness."),
            ("patient", "Je vais essayer cela lors de ma prochaine conversation avec mes parents.", "سأجرب ذلك في محادثتي القادمة مع والديّ.", "I will try this during my next conversation with my parents."),
            ("psychologue", "Bien. Observez leur réaction et notez ce qui a changé dans l'échange.", "جيد. راقب رد فعلهم ودوّن ما تغير في التبادل.", "Good. Observe their reaction and note what changed in the exchange."),
            ("patient", "D'accord, je ferai cet exercice ce week-end.", "حسنًا، سأقوم بهذا التمرين هذا الأسبوع.", "Okay, I will do this exercise this weekend."),
            ("psychologue", "Nous analyserons les résultats ensemble à notre prochaine séance.", "سندون نتائج ذلك معًا في جلستنا القادمة.", "We will analyze the results together at our next session."),
            ("patient", "Merci pour votre aide et votre patience.", "شكراً على مساعدتك وصبرك.", "Thank you for your help and patience."),
            ("psychologue", "Je vous en prie. Le dialogue peut rétablir le lien même après des tensions.", "على الرحب والسعة. الحوار يمكن أن يعيد العلاقات حتى بعد التوترات.", "You're welcome. Dialogue can restore the bond even after tensions."),
        ],
    },
    {
        "id": 19,
        "theme": "Fatigue chronique / énergie",
        "keywords_fr": ["fatigue", "énergie", "épuisement", "sommeil"],
        "messages": [
            ("patient", "Je me sens épuisé tout le temps, même après une nuit de sommeil complète.", "أشعر بالإرهاق طوال الوقت، حتى بعد ليلة نوم كاملة.", "I feel exhausted all the time, even after a full night of sleep."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand ressentez-vous cette fatigue persistante ?", "أهلاً بك. أنا أستمع إليك. منذ متى تشعر بهذا التعب المستمر؟", "Hello. I'm listening. Since when do you feel this persistent fatigue?"),
            ("patient", "Depuis environ six mois. Je n'ai plus d'énergie pour rien, même pour les choses simples.", "منذ حوالي ستة أشهر. لا أملك طاقة لأي شيء، حتى للأشياء البسيطة.", "For about six months. I have no energy for anything, even for simple things."),
            ("psychologue", "Une fatigue persistante peut avoir plusieurs causes. Avez-vous consulté un médecin pour écarter une cause physique ?", "يمكن أن يكون التعب المستمر له أسباب متعددة. هل استشرت طبيبًا لاستبعاد سبب جسدي؟", "Persistent fatigue can have several causes. Have you consulted a doctor to rule out a physical cause?"),
            ("patient", "Oui, les analyses de sang étaient normales. Le médecin n'a rien trouvé d'anormal.", "نعم، كانت تحاليل الدم طبيعية. لم يجد الطبيب شيئًا غير طبيعي.", "Yes, blood tests were normal. The doctor found nothing abnormal."),
            ("psychologue", "Si la cause physique est exclue, la fatigue peut être liée au stress, à l'anxiété ou à une charge émotionnelle importante.", "إذا تم استبعاد السبب الجسدي، يمكن أن يكون التعب مرتبطًا بالتوتر أو القلق أو حمل عاطفي كبير.", "If physical cause is excluded, fatigue can be related to stress, anxiety or significant emotional load."),
            ("patient", "Je traverse effectivement une période stressante au travail et à la maison.", "أمر فعليًا بفترة مرهقة في العمل وفي المنزل.", "I am indeed going through a stressful period at work and at home."),
            ("psychologue", "Nous pouvons travailler sur la gestion de votre énergie et la définition de limites pour vous préserver.", "يمكننا العمل على إدارة طاقتك وتحديد الحدود للحفاظ على نفسك.", "We can work on managing your energy and setting limits to preserve yourself."),
            ("patient", "Je suis prêt à essayer, mais j'ai peur de décevoir les autres si je dis non.", "أنا على استعداد للمحاولة، لكنني أخشى خيبة الآخرين إذا قلت لا.", "I am ready to try, but I'm afraid of disappointing others if I say no."),
            ("psychologue", "Dire non est un acte de soin de soi, pas d'égoïsme. Nous pouvons nous entraîner ensemble à formuler des refus respectueux.", "قول لا هو acto من رعاية الذات، ليست أنانية. يمكننا التدرب معًا على صياغة refus محترمة.", "Saying no is an act of self-care, not selfishness. We can practice together to formulate respectful refusals."),
            ("patient", "Je vais essayer de dire non à une demande cette semaine.", "سأحاول saying لا لطلب هذا الأسبوع.", "I will try to say no to a request this week."),
            ("psychologue", "Bien. Notez comment vous vous sentez après, nous en parlerons ensemble.", "جيد. دوّن كيف تشعر بعد، وسنتحدث عن ذلك معًا.", "Good. Note how you feel after, we will talk about it together."),
            ("patient", "Merci pour vos conseils, je me sens déjà un peu plus léger.", "شكراً على نصائحك، أشعر بأنني أخف قليلاً بالفعل.", "Thank you for your advice, I already feel a little lighter."),
            ("psychologue", "Je vous en prie. Préserver votre énergie est essentiel pour votre bien-être.", "على الرحب والسعة. الحفاظ على طاقتك ضروري لرفاهيتك.", "You're welcome. Preserving your energy is essential for your well-being."),
        ],
    },
    {
        "id": 20,
        "theme": "Questionnement identitaire",
        "keywords_fr": ["identité", "sens de soi", "questionnement", "acceptation"],
        "messages": [
            ("patient", "Je me pose beaucoup de questions sur qui je suis vraiment et ce que je veux dans la vie.", "أطرح العديد من الأسئلة حول من أنا حقًا وما أريده في الحياة.", "I ask myself many questions about who I really am and what I want in life."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand ce questionnement identitaire est-il présent ?", "أهلاً بك. أنا أستمع إليك. منذ متى يوجد هذا التساؤل حول الهوية؟", "Hello. I'm listening. Since when has this identity questioning been present?"),
            ("patient", "Depuis environ un an, depuis que j'ai terminé mes études et commencé ma vie professionnelle.", "منذ حوالي عام، منذ أن أنهيت دراستي وبدأت حياتي المهنية.", "For about a year, since I finished my studies and started my professional life."),
            ("psychologue", "La fin des études est une période de transition où l'on redéfinit souvent son identité. Quelles questions vous préoccupent le plus ?", "نهاية فترة الدراسة هي مرحلة انتقالية حيث يعيد المرء تعريف هويته غالبًا. ما هي الأسئلة التي تشغلك أكثر؟", "The end of studies is a transition period where one often redefines their identity. Which questions concern you most?"),
            ("patient", "Je ne sais pas si je suis sur le bon chemin professionnel et si mes choix reflètent vraiment qui je suis.", "لا أعرف إذا كنت على المسار المهني الصحيح وإذا كانت خياراتي تعكس من أنا حقًا.", "I don't know if I'm on the right professional path and if my choices really reflect who I am."),
            ("psychologue", "C'est une réflexion saine. Avez-vous identifié des valeurs qui sont importantes pour vous ?", "هذا تفكير صحي. هل حددت قيمًا مهمة لك؟", "That's a healthy reflection. Have you identified values that are important to you?"),
            ("patient", "L'autonomie, la créativité et l'aider les autres sont importantes pour moi.", "الاستقلالية، الإبداع ومساعدة الآخرين مهمة بالنسبة لي.", "Autonomy, creativity and helping others are important to me."),
            ("psychologue", "Ce sont de belles valeurs. Comment pourriez-vous les intégrer davantage dans votre quotidien professionnel ?", "هذه قيم جميلة. كيف يمكنك دمجها أكثر في حياتك اليومية المهنية؟", "Those are beautiful values. How could you integrate them more into your daily professional life?"),
            ("patient", "Je pourrais chercher des projets qui allient créativité et aide aux autres.", "يمكنني البحث عن مشاريع تجمع بين الإبداع ومساعدة الآخرين.", "I could look for projects that combine creativity and helping others."),
            ("psychologue", "Excellente idée. Commencez par explorer une petite piste et voyez où cela vous mène.", "فكرة ممتازة. ابدأ باستكشاف مسار صغير وانظر إلى أين يؤدي بك.", "Excellent idea. Start by exploring a small track and see where it leads you."),
            ("patient", "Je vais essayer de consacrer une heure par semaine à cette réflexion.", "سأحاول تخصيص ساعة في الأسبوع لهذه الفكرة.", "I will try to dedicate one hour per week to this reflection."),
            ("psychologue", "Bien. Nous ferons le point sur vos découvertes la prochaine fois.", "جيد. سنقيم اكتشافاتك في المرة القادمة.", "Good. We will review your discoveries next time."),
            ("patient", "Merci pour votre écoute et votre bienveillance.", "شكراً على استماعك ولطفك.", "Thank you for your listening and kindness."),
            ("psychologue", "Je vous en prie. Le chemin vers soi-même est un voyage qui mérite d'être parcouru.", "على الرحب والسعة. الطريق نحو الذات هو رحلة تستحق أن تُقطع.", "You're welcome. The path to oneself is a journey worth taking."),
        ],
    },
    {
        "id": 21,
        "theme": "Peur de l'avenir / incertitude",
        "keywords_fr": ["avenir", "incertitude", "peur", "projection"],
        "messages": [
            ("patient", "J'ai peur de l'avenir. Je ne sais pas ce qui m'attend et cela m'angoisse.", "أخشى المستقبل. لا أعرف ما الذي ينتظرني وهذا يثير قلقي.", "I am afraid of the future. I don't know what awaits me and it angsts me."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand cette peur de l'avenir est-elle présente ?", "أهلاً بك. أنا أستمع إليك. منذ متى يوجد هذا الخوف من المستقبل؟", "Hello. I'm listening. Since when has this fear of the future been present?"),
            ("patient", "Depuis plusieurs mois, surtout depuis les changements récents dans ma vie professionnelle.", "منذ عدة أشهر، خاصة بعد التغييرات الأخيرة في حياتي المهنية.", "For several months, especially since recent changes in my professional life."),
            ("psychologue", "L'incertitude peut générer beaucoup d'anxiété. Que redoutez-vous le plus pour l'avenir ?", "الغموض يمكن أن يولد الكثير من القلق. ماذا تخشاه أكثر للمستقبل؟", "Uncertainty can generate a lot of anxiety. What do you fear most for the future?"),
            ("patient", "De ne pas trouver de stabilité, de ne pas réussir à construire quelque chose de durable.", "من عدم العثور على استقرار، من عدم القدرة على بناء شيء دائم.", "Of not finding stability, of not succeeding in building something durable."),
            ("psychologue", "Le besoin de stabilité est légitime. Concentrez-vous sur ce que vous pouvez contrôler aujourd'hui plutôt que sur l'inconnu lointain.", "الحاجة للاستقرار شرعية. ركز على ما يمكنك السيطرة عليه اليوم بدلاً من المجهول البعيد.", "The need for stability is legitimate. Focus on what you can control today rather than the distant unknown."),
            ("patient", "Je vais essayer de me concentrer sur mes actions quotidiennes plutôt que sur l'avenir lointain.", "سأحاول التركيز على أفعالي اليومية بدلاً من المستقبل البعيد.", "I will try to focus on my daily actions rather than the distant future."),
            ("psychologue", "Bien. Fixez-vous un petit objectif réalisable pour cette semaine et célébrez chaque avancée.", "جيد. حدد هدفًا صغيرًا قابلًا للتحقيق لهذا الأسبوع واحتفل بكل تقدم.", "Good. Set a small achievable goal for this week and celebrate every progress."),
            ("patient", "Je vais essayer de finir un projet qui me tient à cœur cette semaine.", "سأحاول إنهاء مشروع يهمني هذا الأسبوع.", "I will try to finish a project that is close to my heart this week."),
            ("psychologue", "Excellente initiative. Cela vous redonnera un sentiment de contrôle sur votre vie.", "مبادرة ممتازة. سيعيد لك هذا الشعور بالسيطرة على حياتك.", "Excellent initiative. This will give you back a sense of control over your life."),
            ("patient", "Merci pour vos conseils, je me sens un peu plus apaisé.", "شكراً على نصائحك، أشعر بأنني أكثر هدوءًا قليلاً.", "Thank you for your advice, I feel a little more calmed."),
            ("psychologue", "Je vous en prie. L'avenir se construit pas à pas, dans le présent.", "على الرحب والسعة. المستقبل يُبنى خطوة بخطوة، في الحاضر.", "You're welcome. The future is built step by step, in the present."),
            ("patient", "Je me sens déjà un peu plus confiant pour les jours à venir.", "أشعر بالفعل ببعض الثقة أكثر للأيام القادمة.", "I already feel a little more confident for the days to come."),
            ("psychologue", "C'est encourageant. Continuez à avancer avec douceur envers vous-même.", "هذا مشجع. استمر في التقدم بلطف تجاه نفسك.", "That's encouraging. Continue moving forward with gentleness towards yourself."),
        ],
    },
    {
        "id": 22,
        "theme": "Manque de motivation / procrastination",
        "keywords_fr": ["motivation", "procrastination", "objectifs", "action"],
        "messages": [
            ("patient", "Je manque de motivation. Je repousse constamment mes projets et je me sens coupable.", "أفتقر إلى الدافع. أستمر في تأجيل مشاريعي وأشعر بالذنب.", "I lack motivation. I constantly postpone my projects and I feel guilty."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand ce manque de motivation est-il présent ?", "أهلاً بك. أنا أستمع إليك. منذ متى يوجد هذا النقص في الدافع؟", "Hello. I'm listening. Since when has this lack of motivation been present?"),
            ("patient", "Depuis environ quatre mois. Je commence plein de choses mais je ne termine rien.", "منذ حوالي أربعة أشهر. أبدأ الكثير من الأشياء لكنني لا أنهي شيئًا.", "For about four months. I start many things but I finish nothing."),
            ("psychologue", "La procrastination est souvent liée à la peur de l'échec ou au perfectionnisme. Quelles tâches repoussez-vous le plus souvent ?", "التسويف مرتبط غالبًا بخوف الفشل أو الكمال. ما هي المهام التي تؤجلها غالبًا؟", "Procrastination is often linked to fear of failure or perfectionism. Which tasks do you postpone most often?"),
            ("patient", "Principalement les tâches administratives et les projets personnels qui me tiennent à cœur.", "بشكل رئيسي المهام الإدارية والمشاريع الشخصية التي تهمني.", "Mainly administrative tasks and personal projects that are close to my heart."),
            ("psychologue", "Découper un grand projet en petites étapes peut vous aider à démarrer. Quelle est la toute première petite étape pour votre projet le plus important ?", "تقسيم مشروع كبير إلى خطوات صغيرة يمكن أن يساعدك في البدء. ما هي أول خطوة صغيرة لمشروعك الأكثر أهمية؟", "Breaking a large project into small steps can help you start. What is the very first small step for your most important project?"),
            ("patient", "Peut-être simplement ouvrir le document et écrire le titre.", "ربما ببساطة فتح المستند وكتابة العنوان.", "Maybe simply open the document and write the title."),
            ("psychologue", "Parfait. Commencez par cette toute petite action et observez ce qui se passe.", "ممتاز. ابدأ بهذه الخطوة الصغيرة جدًا وراقب ما يحدث.", "Perfect. Start with this very small action and observe what happens."),
            ("patient", "Je vais essayer de faire cela aujourd'hui même.", "سأحاول فعل ذلك اليوم نفسه.", "I will try to do that today itself."),
            ("psychologue", "Bien. Notez ce que vous ressentez après avoir commencé, nous en parlerons ensemble.", "جيد. دوّن ما تشعر به بعد البدء، وسنتحدث عن ذلك معًا.", "Good. Note what you feel after starting, we will talk about it together."),
            ("patient", "D'accord, je tiendrai un petit journal de mes avancées.", "حسنًا، سأحتفظ بسجل صغير لتقديمي.", "Okay, I will keep a small journal of my progress."),
            ("psychologue", "C'est une bonne méthode pour reprendre confiance en votre capacité à agir.", "هذه طريقة جيدة لاستعادة الثقة في قدرتك على العمل.", "That's a good method to regain confidence in your ability to act."),
            ("patient", "Merci pour vos conseils, je me sens déjà un peu plus motivé.", "شكراً على نصائحك، أشعر بأنني أكثر تحفيزًا قليلاً.", "Thank you for your advice, I already feel a little more motivated."),
            ("psychologue", "Je vous en prie. Chaque petite action compte vers vos objectifs.", "على الرحب والسعة. كل إجراء صغير يهم نحو أهدافك.", "You're welcome. Every small action counts towards your goals."),
        ],
    },
    {
        "id": 23,
        "theme": "Anxiété de séparation",
        "keywords_fr": ["séparation", "attachement", "peur", "lien"],
        "messages": [
            ("patient", "J'ai du mal quand mes proches s'absentent. Je m'inquiète constamment pour eux.", "أعاني عندما يغيب أحبائي. أقلق باستمرار عليهم.", "I have a hard time when my loved ones are away. I constantly worry about them."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand ressentez-vous cette anxiété de séparation ?", "أهلاً بك. أنا أستمع إليك. منذ متى تشعر بهذا القلق من الانفصال؟", "Hello. I'm listening. Since when do you feel this separation anxiety?"),
            ("patient", "Depuis longtemps, mais cela s'est aggravé depuis le départ de mon enfant pour ses études.", "منذ زمن طويل، لكنه تفاقم منذ مغادرة طفله دراسته.", "For a long time, but it has worsened since my child left for studies."),
            ("psychologue", "Le nid qui se vide est une étape émotionnelle importante. Que vous dites-vous lorsque votre enfant est absent ?", "عش فارغ هو مرحلة عاطفية مهمة. ما الذي تقوله لنفسك عندما يكون طفلك غائبًا؟", "The empty nest is an important emotional stage. What do you tell yourself when your child is absent?"),
            ("patient", "Je me dis qu'il pourrait lui arriver quelque chose et que je ne serais pas là pour l'aider.", "أقول لنفسي أنه قد يحدث له شيء ولن أكون هناك لمساعدته.", "I tell myself something could happen to him and I wouldn't be there to help him."),
            ("psychologue", "Ce scénario catastrophe alimente l'anxiété. Avez-vous des preuves concrètes que quelque chose de mauvais lui arrivera ?", "هذا السيناريو الكارثي يغذي القلق. هل لديك أدلة ملموسة أن شيئًا سيئًا سيحدث له؟", "This catastrophic scenario fuels anxiety. Do you have concrete evidence that something bad will happen to him?"),
            ("patient", "Non, c'est juste mes craintes, mais elles semblent très réelles.", "لا، إنها مجرد مخاوفي، لكنها تبدو حقيقية جدًا.", "No, it's just my fears, but they seem very real."),
            ("psychologue", "Nous pouvons travailler à remettre en question ces pensées et à développer une confiance dans l'autonomie de votre enfant.", "يمكننا العمل على التشكيك في هذه الأفكار وتطوير ثقة في استقلالية طفلك.", "We can work on questioning these thoughts and developing confidence in your child's autonomy."),
            ("patient", "Je suis prêt à essayer, mais c'est difficile de lâcher prise.", "أنا على استعداد للمحاولة، لكن من الصعب التخلي.", "I am ready to try, but it is difficult to let go."),
            ("psychologue", "C'est compréhensible. Lâcher prise ne signifie pas abandonner, mais faire confiance.", "هذا مفهوم. التخلي لا يعني التخلي، بل الثقة.", "That's understandable. Letting go does not mean abandoning, but trusting."),
            ("patient", "Je vais essayer de m'appuyer sur cette idée quand l'anxiété monte.", "سأحاول الاعتماد على هذه الفكرة عندما يرتفع القلق.", "I will try to rely on this idea when anxiety rises."),
            ("psychologue", "Bien. Nous ferons le point sur vos progrès la prochaine fois.", "جيد. سنقيم تقدمك في المرة القادمة.", "Good. We will review your progress next time."),
            ("patient", "Merci pour votre soutien et votre compréhension.", "شكراً على دعمك وتفهمك.", "Thank you for your support and understanding."),
            ("psychologue", "Je vous en prie. Vous avancez vers plus de sérénité.", "على الرحب والسعة. أنت تتقدم نحو المزيد من السكينة.", "You're welcome. You are moving towards more serenity."),
        ],
    },
    {
        "id": 24,
        "theme": "Troubles du sommeil (cauchemars)",
        "keywords_fr": ["cauchemars", "sommeil", "nuit", "rêves"],
        "messages": [
            ("patient", "Je fais des cauchemars fréquents qui me réveillent en pleine nuit.", "أعاني من كوابيس متكررة توقظني في منتصف الليل.", "I have frequent nightmares that wake me up in the middle of the night."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand faites-vous ces cauchemars ?", "أهلاً بك. أنا أستمع إليك. منذ متى ترى هذه الكوابيس؟", "Hello. I'm listening. Since when do you have these nightmares?"),
            ("patient", "Depuis environ trois mois. Je me réveille en sueur et j'ai du mal à me rendormir.", "منذ حوالي ثلاثة أشهر. أستيقظ متعرقًا وأصعب في العودة للنوم.", "For about three months. I wake up sweating and have trouble falling back asleep."),
            ("psychologue", "Les cauchemars peuvent être liés au stress ou à des événements difficiles récents. De quoi parlent-ils souvent ?", "يمكن أن تكون الكوابيس مرتبطة بالتوتر أو بأحداث صعبة récente. عن ماذا تتحدث غالبًا؟", "Nightmares can be linked to stress or recent difficult events. What do they often talk about?"),
            ("patient", "Je rêve souvent que je perds quelqu'un d'important ou que je suis dans une situation dangereuse.", "أحلم غالبًا بأنني أفقد شخصًا مهمًا أو أنني في موقف خطير.", "I often dream that I lose someone important or that I am in a dangerous situation."),
            ("psychologue", "Ces rêves reflètent souvent des peurs profondes. Avez-vous déjà essayé d'écrire vos rêves dès le réveil pour mieux les comprendre ?", "غالبًا ما تعكس هذه الأحلام مخاوف عميقة. هل جربت كتابة أحلامك فور الاستيقاظ لفهمها بشكل أفضل؟", "These dreams often reflect deep fears. Have you tried writing down your dreams as soon as you wake up to understand them better?"),
            ("patient", "Non, mais je suis prêt à essayer.", "لا، لكنني على استعداد للمحاولة.", "No, but I am ready to try."),
            ("psychologue", "Tenez un journal des rêves à côté de votre lit et notez ce dont vous vous souvenez dès le réveil.", "احتفظ بمذكرة أحلام بجانب سريرك ودوّن ما تتذكره فور الاستيقاظ.", "Keep a dream journal next to your bed and note what you remember as soon as you wake up."),
            ("patient", "Je vais essayer cela cette nuit.", "سأجرب ذلك الليلة.", "I will try that tonight."),
            ("psychologue", "Bien. Vous pouvez aussi pratiquer une relaxation douce avant de vous endormir pour apaiser votre esprit.", "جيد. يمكنك أيضًا ممارسة استرخاء خفيف قبل النوم لتهدئة عقلك.", "Good. You can also practice gentle relaxation before falling asleep to calm your mind."),
            ("patient", "Je vais essayer une courte méditation avant de dormir.", "سأحاول تأمل قصير قبل النوم.", "I will try a short meditation before sleeping."),
            ("psychologue", "Excellent. Nous analyserons vos rêves ensemble à notre prochaine séance.", "ممتاز. سندون أحلامك معًا في جلستنا القادمة.", "Excellent. We will analyze your dreams together at our next session."),
            ("patient", "Merci pour vos conseils, je me sens déjà un peu plus serein.", "شكراً على نصائحك، أشعر بأنني أكثر سكينة قليلاً.", "Thank you for your advice, I already feel a little more serene."),
            ("psychologue", "Je vous en prie. Prenez soin de votre sommeil, il est essentiel.", "على الرحب والسعة. اعتني بنومك،他是 ضروري.", "You're welcome. Take care of your sleep, it is essential."),
        ],
    },
    {
        "id": 25,
        "theme": "Stress financier",
        "keywords_fr": ["argent", "dettes", "stress", "budget"],
        "messages": [
            ("patient", "Je suis stressé par ma situation financière. Je n'arrive pas à joindre les deux bouts chaque mois.", "أنا متوتر بشأن وضعي المالي. لا أستطيع تلبية احتياجاتي كل شهر.", "I am stressed about my financial situation. I can't make ends meet every month."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand cette situation financière est-elle difficile ?", "أهلاً بك. أنا أستمع إليك. منذ متى يكون وضعك المالي صعبًا؟", "Hello. I'm listening. Since when has your financial situation been difficult?"),
            ("patient", "Depuis environ un an, depuis ma perte d'emploi et mes dettes qui s'accumulent.", "منذ حوالي عام، منذ فقدان وظيفتي وديني التي تتراكم.", "For about a year, since my job loss and my accumulating debts."),
            ("psychologue", "La perte d'emploi est un facteur de stress majeur. Avez-vous établi un budget pour voir clairement vos entrées et sorties d'argent ?", "فقدان الوظيفة هو عامل إجهاد كبير. هل أعددت ميزانية لترى دخلك ونفقاتك بوضوح؟", "Job loss is a major stress factor. Have you established a budget to clearly see your income and expenses?"),
            ("patient", "Non, j'évite de regarder mes comptes parce que cela m'angoisse davantage.", "لا، أتجنب النظر إلى حساباتي لأنه يزيد قلقي.", "No, I avoid looking at my accounts because it angsts me further."),
            ("psychologue", "L'évitement augmente le stress à long terme. Nous pourrions commencer par lister ensemble vos dépenses principales.", "التجنب يزيد الإجهاد على المدى الطويل. يمكننا البدء بإدراج نفقاتك الرئيسية معًا.", "Avoidance increases stress long-term. We could start by listing together your main expenses."),
            ("patient", "Je suis prêt à essayer, mais j'ai peur de ce que je vais découvrir.", "أنا على استعداد للمحاولة، لكنني أخشى ما سأكتشف.", "I am ready to try, but I'm afraid of what I will discover."),
            ("psychologue", "C'est compréhensible. Connaître sa situation est le premier pas pour reprendre le contrôle.", "هذا مفهوم. معرفة وضعك هي الخطوة الأولى لاستعادة السيطرة.", "That's understandable. Knowing your situation is the first step to regaining control."),
            ("patient", "Je vais essayer de lister mes dépenses principales ce week-end.", "سأحاول إدراج نفقات main هذا الأسبوع.", "I will try to list my main expenses this weekend."),
            ("psychologue", "Bien. Nous analyserons cette liste ensemble et chercherons des solutions concrètes.", "جيد. سندون هذه القائمة معًا ونبحث عن حلول ملموسة.", "Good. We will analyze this list together and look for concrete solutions."),
            ("patient", "Merci pour votre aide, je me sens déjà un peu moins accablé.", "شكراً على مساعدتك، أشعر بأنني أقل إرهاقًا قليلاً.", "Thank you for your help, I already feel a little less overwhelmed."),
            ("psychologue", "Je vous en prie. Une étape à la fois, vous avancerez vers plus de stabilité.", "على الرحب والسعة. خطوة واحدة في كل مرة، ستتقدم نحو استقرار أكبر.", "You're welcome. One step at a time, you will move towards more stability."),
        ],
    },
    {
        "id": 26,
        "theme": "Difficulté à dire non / boundaries",
        "keywords_fr": ["dire non", "boundaries", "affirmation de soi", "respect"],
        "messages": [
            ("patient", "J'ai du mal à dire non aux autres. J'accepte toujours tout et je me sens dépassé.", "أعاني في قول لا للآخرين. أقبل دائمًا كل شيء وأشعر بالإرهاق.", "I have trouble saying no to others. I always accept everything and I feel overwhelmed."),
            ("psychologue", "Bonjour. Je vous écoute. Dans quelles situations avez-vous le plus de mal à dire non ?", "أهلاً بك. أنا أستمع إليك. في أي المواقف تواجه صعوبة أكبر في قول لا؟", "Hello. I'm listening. In which situations do you have the most trouble saying no?"),
            ("patient", "Principalement avec mes collègues et ma famille. Je ne veux pas les décevoir ou créer des conflits.", "بشكل رئيسي مع زملائي وعائلتي. لا أريد خيبة أملهم أو خلق صراعات.", "Mainly with my colleagues and family. I don't want to disappoint them or create conflicts."),
            ("psychologue", "Le besoin de plaire peut mener à l'épuisement. Dire non est un acte de respect envers soi-même.", "الحاجة لإرضاء الآخرين يمكن أن تؤدي إلى الإرهاق. قول لا هو acto من احترام الذات.", "The need to please can lead to exhaustion. Saying no is an act of self-respect."),
            ("patient", "Je comprends, mais je ne sais pas comment formuler un refus sans être impoli.", "أفهم، لكنني لا أعرف كيف أهدر رفض دون أن أكون فظًا.", "I understand, but I don't know how to formulate a refusal without being rude."),
            ("psychologue", "Vous pouvez dire : 'Je comprends votre demande, mais je ne peux pas y répondre pour le moment.' C'est clair et respectueux.", "يمكنك قول: 'أفهم طلبك، لكنني لا أستطيع الاستجابة له في الوقت الحالي.' هذا واضح ومحترم.", "You can say: 'I understand your request, but I cannot respond to it for the moment.' It is clear and respectful."),
            ("patient", "Je vais essayer d'utiliser cette phrase la prochaine fois qu'on me demande quelque chose.", "سأحاول استخدام هذه الجملة في المرة القادمة التي يُطلب مني فيها شيء.", "I will try to use this phrase next time someone asks me something."),
            ("psychologue", "Bien. Observez leur réaction et notez ce que vous ressentez après avoir dit non.", "جيد. راقب رد فعلهم ودوّن ما تشعر به بعد قول لا.", "Good. Observe their reaction and note what you feel after saying no."),
            ("patient", "D'accord, je ferai cet exercice cette semaine.", "حسنًا، سأقوم بهذا التمرين هذا الأسبوع.", "Okay, I will do this exercise this week."),
            ("psychologue", "Nous analyserons les résultats ensemble à notre prochaine séance.", "سندون نتائج ذلك معًا في جلستنا القادمة.", "We will analyze the results together at our next session."),
            ("patient", "Merci pour votre soutien, je me sens déjà un peu plus fort.", "شكراً على دعمك، أشعر بأنني أقوى قليلاً.", "Thank you for your support, I already feel a little stronger."),
            ("psychologue", "Je vous en prie. L'affirmation de soi s'apprend avec la pratique.", "على الرحب والسعة. التأكيد على الذات تتعلم بالممارسة.", "You're welcome. Self-affirmation is learned with practice."),
        ],
    },
    {
        "id": 27,
        "theme": "Nostalgie / regret",
        "keywords_fr": ["nostalgie", "regret", "passé", "mémoire"],
        "messages": [
            ("patient", "Je ressens beaucoup de nostalgie pour mon passé. Je repense souvent à des moments heureux qui ne reviendront jamais.", "أشعر بالكثير من الحنين إلى ماضي. أفكر غالبًا في لحظات سعيدة لن تعود أبدًا.", "I feel a lot of nostalgia for my past. I often think about happy moments that will never return."),
            ("psychologue", "Bonjour. Je vous écoute. Quels moments du passé vous manquent le plus ?", "أهلاً بك. أنا أستمع إليك. أي لحظات من الماضي تفتقدها أكثر؟", "Hello. I'm listening. Which moments from the past do you miss most?"),
            ("patient", "Principalement mes années d'études et les amitiés de cette époque.", "بشكل رئيسي سنوات دراستي وصداقات تلك الفترة.", "Mainly my years of study and the friendships of that time."),
            ("psychologue", "La nostalgie peut être douce-amère. Elle nous rappelle ce qui a compté, mais peut aussi nous empêcher d'avancer.", "يمكن أن يكون الحنين مريرًا حلوًا. يذكرنا بما كان مهمًا، لكنه قد يمنعنا أيضًا من التقدم.", "Nostalgia can be bittersweet. It reminds us of what mattered, but can also prevent us from moving forward."),
            ("patient", "J'aimerais pouvoir revenir en arrière, mais je sais que c'est impossible.", "أود أن أتمكن من العودة إلى الوراء، لكنني أعلم أنه مستحيل.", "I would like to be able to go back, but I know it's impossible."),
            ("psychologue", "Accepter que le passé est derrière nous est difficile mais nécessaire. Que pourriez-vous faire aujourd'hui pour créer de nouveaux souvenirs heureux ?", "قبول أن الماضي وراءنا صعب لكنه ضروري. ما الذي يمكنك فعله اليوم لخلق ذكريات سعيدة جديدة؟", "Accepting that the past is behind us is difficult but necessary. What could you do today to create new happy memories?"),
            ("patient", "Je pourrais reprendre contact avec un ancien ami ou essayer une nouvelle activité.", "يمكنني الاتصال بصديق قديم أو تجربة نشاط جديد.", "I could get back in touch with an old friend or try a new activity."),
            ("psychologue", "Excellente idée. Commencez par une petite action et observez comment vous vous sentez après.", "فكرة ممتازة. ابدأ بإجراء صغير وراقب كيف تشعر بعد.", "Excellent idea. Start with a small action and observe how you feel after."),
            ("patient", "Je vais essayer d'appeler un ami cette semaine.", "سأحاول الاتصال بصديق هذا الأسبوع.", "I will try to call a friend this week."),
            ("psychologue", "Bien. Nous ferons le point sur vos progrès la prochaine fois.", "جيد. سنقيم تقدمك في المرة القادمة.", "Good. We will review your progress next time."),
            ("patient", "Merci pour votre écoute, je me sens déjà un peu plus léger.", "شكراً على استماعك، أشعر بأنني أخف قليلاً.", "Thank you for your listening, I already feel a little lighter."),
            ("psychologue", "Je vous en prie. Le passé fait partie de vous, mais le présent vous appartient.", "على الرحب والسعة. الماضي جزء منك، pero الحاضر ملكك.", "You're welcome. The past is part of you, but the present belongs to you."),
        ],
    },
    {
        "id": 28,
        "theme": "Stress financier",
        "keywords_fr": ["argent", "budget", "dettes", "sécurité"],
        "messages": [
            ("patient", "Je suis inquiet pour mes finances. Mes dettes augmentent et je ne vois pas comment m'en sortir.", "أنا قلق بشأن أموالي. ديوني تزداد ولا أرى كيف يمكنني الخروج منها.", "I am worried about my finances. My debts are increasing and I don't see how to get out."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand vos dettes s'accumulent-elles ?", "أهلاً بك. أنا أستمع إليك. منذ متى تتراكم ديونك؟", "Hello. I'm listening. Since when have your debts been accumulating?"),
            ("patient", "Depuis environ deux ans, depuis mon divorce et mes frais juridiques.", "منذ حوالي عامين، منذ طلاقي ومصاريفنا القانونية.", "For about two years, since my divorce and legal fees."),
            ("psychologue", "Un divorce peut avoir des conséquences financières lourdes. Avez-vous établi un plan de remboursement avec vos créanciers ?", "يمكن أن يكون للطلاق عواقب مالية ثقيلة. هل أعددت خطة سداد مع دائنيك؟", "A divorce can have heavy financial consequences. Have you established a repayment plan with your creditors?"),
            ("patient", "Non, je n'ose pas les contacter parce que j'ai honte de ma situation.", "لا، لا أجرؤ على الاتصال بهم لأنني أشعر بالخجل من وضعي.", "No, I don't dare contact them because I'm ashamed of my situation."),
            ("psychologue", "La honte est un sentiment fréquent, mais les créanciers sont souvent ouverts à des arrangements si on les contacte.", "الخجل شعور متكرر، لكن الدائنين غالبًا ما يكونون منفتحين على الترتيبات إذا تم الاتصال بهم.", "Shame is a frequent feeling, but creditors are often open to arrangements if contacted."),
            ("patient", "Je vais essayer de les contacter cette semaine pour discuter d'un échéancier.", "سأحاول الاتصال بهم هذا الأسبوع لمناقشة جدول سداد.", "I will try to contact them this week to discuss a payment schedule."),
            ("psychologue", "Bien. Préparez une liste de vos dettes et de vos revenus avant de les appeler.", "جيد. أعد قائمة بديونك وإيراداتك قبل الاتصال بهم.", "Good. Prepare a list of your debts and income before calling them."),
            ("patient", "Je vais faire cela ce week-end.", "سأفعل ذلك هذا الأسبوع.", "I will do this this weekend."),
            ("psychologue", "Nous ferons le point sur vos démarches la prochaine fois.", "سنقيم جهودك في المرة القادمة.", "We will review your steps next time."),
            ("patient", "Merci pour votre aide, je me sens déjà un peu moins seul face à cela.", "شكراً على مساعدتك، أشعر بأنني أقل وحدة في مواجهة هذا.", "Thank you for your help, I already feel a little less alone facing this."),
            ("psychologue", "Je vous en prie. Une étape à la fois, vous avancerez vers plus de sécurité financière.", "على الرحب والسعة. خطوة واحدة في كل مرة، ستتقدم نحو أمان مالي أكبر.", "You're welcome. One step at a time, you will move towards more financial security."),
        ],
    },
    {
        "id": 29,
        "theme": "Anxiété santé / hypocondrie légère",
        "keywords_fr": ["santé", "anxiété", "symptômes", "réassurance"],
        "messages": [
            ("patient", "Je m'inquiète souvent pour ma santé. Je vérifie mes symptômes sur internet et je m'angoisse.", "أقلق كثيرًا بشأن صحتي. أتحقق من أعراضي على الإنترنت وأقلق.", "I often worry about my health. I check my symptoms on the internet and I angst."),
            ("psychologue", "Bonjour. Je vous écoute. Depuis quand faites-vous ces recherches sur internet ?", "أهلاً بك. أنا أستمع إليك. منذ متى تجري هذه الأبحاث على الإنترنت؟", "Hello. I'm listening. Since when do you do these internet searches?"),
            ("patient", "Depuis environ six mois. Chaque petite douleur me fait penser au pire.", "منذ حوالي ستة أشهر. كل ألم صغير يجعلني أفكر في الأسوأ.", "For about six months. Every little pain makes me think of the worst."),
            ("psychologue", "L'auto-diagnostic sur internet peut alimenter l'anxiété plutôt que de la rassurer. Avez-vous consulté un médecin récemment pour un bilan général ?", "يمكن أن يزيد التشخيص الذاتي على الإنترنت من القلق بدلاً من طمأنته. هل استشرت طبيبًا مؤخرًا لفحص عام؟", "Self-diagnosis on the internet can fuel anxiety rather than reassure. Have you consulted a doctor recently for a general check-up?"),
            ("patient", "Oui, tout était normal, mais je continue de m'inquiéter.", "نعم، كان كل شيء طبيعيًا، لكنني أستمر في القلق.", "Yes, everything was normal, but I continue to worry."),
            ("psychologue", "Lorsque les examens médicaux sont normaux, l'anxiété peut se maintenir par des pensées catastrophistes. Nous pouvons travailler à limiter ces recherches.", "عندما تكون الفحوصات الطبية طبيعية، يمكن أن يستمر القلق من خلال أفكار كارثية. يمكننا العمل على تقييد هذه الأبحاث.", "When medical exams are normal, anxiety can be maintained by catastrophic thoughts. We can work on limiting these searches."),
            ("patient", "Je suis prêt à essayer de limiter mes recherches sur internet.", "أنا على استعداد للمحاولة لتحديد أبحاثي على الإنترنت.", "I am ready to try to limit my internet searches."),
            ("psychologue", "Fixez-vous une règle : une seule recherche par semaine maximum, et uniquement après avoir consulté un médecin si nécessaire.", "ضع لنفسك قاعدة: بحث واحد في الأسبوع كحد أقصى، وفقط بعد استشارة طبيب إذا لزم الأمر.", "Set yourself a rule: one search per week maximum, and only after consulting a doctor if necessary."),
            ("patient", "Je vais essayer de respecter cette règle à partir de cette semaine.", "سأحاول الالتزام بهذه القاعدة من هذا الأسبوع.", "I will try to respect this rule starting this week."),
            ("psychologue", "Bien. Notez votre niveau d'anxiété avant et après chaque recherche pour voir l'impact.", "جيد. دوّن مستوى قلقك قبل وبعد كل بحث لرؤية التأثير.", "Good. Note your anxiety level before and after each search to see the impact."),
            ("patient", "D'accord, je tiendrai un petit registre de cela.", "حسنًا، سأحتفظ بسجل صغير لذلك.", "Okay, I will keep a small record of this."),
            ("psychologue", "Nous analyserons ces notes ensemble à notre prochaine séance.", "سندون هذه الملاحظات معًا في جلستنا القادمة.", "We will analyze these notes together at our next session."),
            ("patient", "Merci pour votre aide, je me sens déjà un peu plus rassuré.", "شكراً على مساعدتك، أشعر بأنني أكثر طمأنة قليلاً.", "Thank you for your help, I already feel a little more reassured."),
            ("psychologue", "Je vous en prie. Votre santé mentale mérite autant d'attention que votre santé physique.", "على الرحب والسعة. صحتك العقلية تستحق اهتمامًا بقدر صحتك الجسدية.", "You're welcome. Your mental health deserves as much attention as your physical health."),
        ],
    },
    {
        "id": 30,
        "theme": "Reprise après dépression / rémission",
        "keywords_fr": ["rémission", "reprise", "espoir", "progrès"],
        "messages": [
            ("patient", "Je sors d'une période dépressive et je tente de reprendre le cours de ma vie progressivement.", "أنا أخرج من فترة اكتئاب وأحاول استئناف مسار حياتي تدريجياً.", "I am coming out of a depressive period and I try to resume the course of my life gradually."),
            ("psychologue", "Bonjour. Je vous écoute. Comment vous sentez-vous aujourd'hui par rapport à il y a quelques semaines ?", "أهلاً بك. أنا أستمع إليك. كيف تشعر اليوم مقارنة بعدة أسابيع مضت؟", "Hello. I'm listening. How do you feel today compared to a few weeks ago?"),
            ("patient", "Un peu mieux. J'ai retrouvé un peu d'énergie et je recommence à sortir voir des amis.", "بشكل أفضل قليلاً. استعدت بعض الطاقة وبدأت في الخروج لرؤية أصدقاء.", "A little better. I regained a little energy and I'm starting to go out to see friends again."),
            ("psychologue", "C'est un progrès encourageant. Quelles activités vous font du bien en ce moment ?", "هذا تقدم مشجع. ما هي الأنشطة التي تجعلك تشعر بالتحسن في الوقت الحالي؟", "That's an encouraging progress. What activities make you feel good right now?"),
            ("patient", "Marcher dans le parc, lire un livre et cuisiner des repas simples.", "المشي في الحديقة، قراءة كتاب وطهي وجبات بسيطة.", "Walking in the park, reading a book and cooking simple meals."),
            ("psychologue", "Ce sont de belles activités de reprise. Continuez à les pratiquer régulièrement sans vous mettre trop de pression.", "هذه أنشطة جميلة للاستئناف. استمر في ممارستها بانتظام دون وضع ضغط كبير على نفسك.", "These are nice resumption activities. Continue practicing them regularly without putting too much pressure on yourself."),
            ("patient", "J'ai peur de rechuter si je vais trop vite.", "أخشى الانتكاس إذا سريعت كثيرًا.", "I'm afraid of relapsing if I go too fast."),
            ("psychologue", "La peur de la rechute est légitime. Avancez à votre rythme et écoutez vos signes de fatigue.", "خوف الانتكاس شرعي. تقدم بوتيرتك واستمع لعلامات إرهاقك.", "The fear of relapse is legitimate. Move at your pace and listen to your fatigue signs."),
            ("patient", "Je vais essayer d'être plus à l'écoute de mes limites.", "سأحاول الاستماع أكثر لحدودي.", "I will try to listen more to my limits."),
            ("psychologue", "Bien. Nous ferons le point sur vos progrès et vos besoins la prochaine fois.", "جيد. سنقيم تقدمك واحتياجاتك في المرة القادمة.", "Good. We will review your progress and needs next time."),
            ("patient", "Merci pour votre soutien, je me sens déjà un peu plus espoir.", "شكراً على دعمك، أشعر بأنني أكثر أملاً قليلاً.", "Thank you for your support, I already feel a little more hope."),
            ("psychologue", "Je vous en prie. Chaque jour est une nouvelle opportunité pour avancer vers votre bien-être.", "على الرحب والسعة. كل يوم هو فرصة جديدة للتقدم نحو رفاهيتك.", "You're welcome. Every day is a new opportunity to move towards your well-being."),
        ],
    },
]


def create_users(num_patients=90, num_psychologists=30):
    """Crée des utilisateurs dédiés pour le seeding s'ils n'existent pas déjà."""
    created = 0
    for i in range(num_psychologists):
        username = f"seed_psy_{i+1:03d}"
        if not CustomUser.objects.filter(username=username).exists():
            CustomUser.objects.create_user(
                username=username,
                password="seed_password_123",
                user_type="psychologue",
                first_name=f"PsySeed{i+1}",
                last_name="Test",
                preferred_language="fr",
            )
            created += 1
    for i in range(num_patients):
        username = f"seed_pat_{i+1:03d}"
        if not CustomUser.objects.filter(username=username).exists():
            CustomUser.objects.create_user(
                username=username,
                password="seed_password_123",
                user_type="patient",
                first_name=f"PatSeed{i+1}",
                last_name="Test",
                preferred_language="fr",
            )
            created += 1
    return created


def get_content(msg, lang):
    """Retourne le contenu d'un message dans la langue demandée."""
    role, fr, ar, en = msg
    if lang == "fr":
        return fr
    if lang == "ar":
        return ar
    return en


def seed():
    CustomUser = get_user_model()
    psychologists = list(
        CustomUser.objects.filter(user_type="psychologue").order_by("id")
    )
    patients = list(CustomUser.objects.filter(user_type="patient").order_by("id"))

    if len(psychologists) < 30 or len(patients) < 90:
        print(
            "Erreur: pas assez d'utilisateurs. Lancez d'abord la création des utilisateurs."
        )
        return

    total_conversations = 0
    total_messages = 0

    for idx, scenario in enumerate(SCENARIOS):
        psycho = psychologists[idx % len(psychologists)]
        for lang in ("fr", "ar", "en"):
            patient = patients[total_conversations % len(patients)]
            conv, _ = Conversation.objects.get_or_create(
                psychologue=psycho,
                patient=patient,
            )
            for pos, msg in enumerate(scenario["messages"]):
                role = msg[0]
                sender = patient if role == "patient" else psycho
                content = get_content(msg, lang)
                Message.objects.create(
                    conversation=conv,
                    sender=sender,
                    content=content,
                )
            total_conversations += 1
            total_messages += len(scenario["messages"])

    print(f"Conversations créées: {total_conversations}")
    print(f"Messages créés: {total_messages}")


if __name__ == "__main__":
    print("=== Seed des utilisateurs ===")
    nb_users = create_users()
    print(f"Utilisateurs créés: {nb_users}")
    print("")
    print("=== Seed des conversations et messages ===")
    seed()
    print("Terminé.")