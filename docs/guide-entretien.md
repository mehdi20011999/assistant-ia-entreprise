# Guide d'entretien : expliquer ce projet

Avant d'ajouter ce projet à ton CV, tu dois pouvoir répondre à chaque question ci-dessous sans regarder le code.
Lance `make run`, essaie chaque rôle dans l'interface, puis lis `app/rag.py` de haut en bas : c'est tout le pipeline en 80 lignes.

## Le pitch (30 secondes)

« J'ai construit un assistant IA qui répond aux questions des salariés à partir des documents internes, avec les garde-fous
qu'une entreprise exige avant de le déployer : réponses sourcées, contrôle d'accès par rôle, masquage des données personnelles
pour la loi 09-08, blocage des injections de prompt et journal d'audit. Une évaluation de 29 questions tourne dans la CI et
bloque toute modification qui fait baisser la qualité ou crée une fuite. »

## Questions probables

**Qu'est-ce qu'un RAG, et pourquoi pas simplement un LLM ?**
RAG veut dire *Retrieval-Augmented Generation* : on cherche d'abord les passages pertinents dans les documents, puis on
demande au modèle de répondre **uniquement** à partir d'eux. Un LLM seul ne connaît pas les procédures internes et invente
une réponse plausible. Le RAG apporte trois choses : des informations à jour, des sources vérifiables, et la possibilité de
contrôler ce que le modèle a le droit de lire.

**Pourquoi le contrôle d'accès se fait-il avant la recherche, et pas après ?**
Si on filtre après, le document confidentiel a déjà été lu et peut se retrouver dans la réponse, ou influencer le classement.
En filtrant avant (`retriever.search`, ligne `visibles = ...`), un document interdit n'existe tout simplement pas pour ce rôle.
Le test `test_controle_acces_avant_classement` le vérifie.

**Pourquoi BM25 et pas des embeddings ?**
BM25 est une recherche par mots-clés pondérés : rapide, explicable, sans modèle à télécharger, et très efficace sur des
documents administratifs où les mots exacts comptent (« télétravail », « note de frais »). Sa limite, ce sont les synonymes et
les reformulations. L'amélioration naturelle est une recherche hybride, BM25 et embeddings multilingues.

**Comment évitez-vous les hallucinations ?**
Trois barrières : on refuse si aucun passage n'est assez pertinent (score et couverture de la question) ; la consigne impose
de citer chaque information ; et le code vérifie que les citations renvoient à des extraits réellement fournis. Sinon il refuse
(`test_citation_inventee_refusee`).

**Que se passe-t-il si quelqu'un écrit « ignore tes instructions » ?**
Le garde-fou bloque la question avant toute recherche. Et même s'il laissait passer une variante, deux protections restent :
le rôle ne donne jamais accès à des documents interdits, quoi que dise la question, et la consigne traite les extraits comme
des données, pas comme des ordres. La détection par motifs ne suffit pas seule, d'où cette défense en profondeur.

**Pourquoi masquer les données personnelles avant le modèle, et pas seulement dans la réponse ?**
Parce qu'avec une API externe, tout ce qu'on envoie quitte l'entreprise. La loi 09-08 encadre le transfert de données
personnelles : en masquant avant l'appel, le fournisseur ne voit jamais un numéro de téléphone ou une CIN.

**Pourquoi trois moteurs (extractif, Ollama, OpenAI) ?**
Pour laisser le choix à l'entreprise entre coût, qualité et souveraineté. Le moteur extractif ne coûte rien, ne fait sortir
aucune donnée et sert de secours si le modèle tombe. Ollama fait tourner un LLM open source dans l'entreprise. Une API
compatible OpenAI donne les meilleures réponses, mais avec un coût et un transfert de données.

**Comment savez-vous que le système ne se dégrade pas ?**
L'évaluation tourne à chaque push et bloque la CI si un seuil n'est pas atteint : par exemple, une seule fuite de document
confidentiel suffit à faire échouer le build. Limite honnête : les questions ont été écrites avec le système. En entreprise,
il faudrait y ajouter de vraies questions de salariés.

**Comment le surveilleriez-vous en production ?**
Les métriques Prometheus (`/metrics`) donnent le volume par statut et la latence : une hausse des refus signale des documents
manquants, une hausse des blocages signale une attaque. Le journal d'audit permet d'enquêter question par question.

**Comment avez-vous optimisé la recherche ?**
Au départ, chaque question notait tous les passages : le coût grandissait avec la taille de la base. J'ai construit un
index inversé (pour chaque mot, la liste des passages qui le contiennent) : on ne note que les passages concernés.
Avec les normalisations pré-calculées et un top-k par tas, la latence médiane est passée de 11,8 ms à environ 2,5 ms sur
29 000 passages. Un test compare les scores avec le calcul naïf pour prouver que le résultat est identique.

**Pourquoi masquer les données personnelles au chargement plutôt qu'à chaque requête ?**
C'est plus rapide (une fois au lieu de chaque fois) et plus sûr : les numéros ne sont même pas dans l'index, donc on ne
peut pas les retrouver en les cherchant. C'est le principe de protection des données dès la conception.

**Pourquoi HMAC pour pseudonymiser l'utilisateur, et pas un simple hash ?**
Un hash sans secret se recalcule par n'importe qui : avec une liste de clés ou d'identifiants, on retrouve qui a posé
quelle question. Avec HMAC, il faut le secret, conservé dans un coffre, hors du journal.

**Que se passe-t-il avec plusieurs processus ou plusieurs serveurs ?**
La limitation de débit et les métriques sont en mémoire, donc propres à chaque processus. Pour passer à l'échelle, on les
déplace dans Redis, puis on augmente le nombre de processus. C'est écrit dans le Dockerfile.

## Exercices pour te l'approprier

1. Ajoute un document `rh-formation.md` (accès `employe`) et une question d'évaluation dessus. Lance `make eval`.
2. Crée un rôle `finance` qui voit un nouveau document confidentiel, et vérifie qu'un employé ne le voit pas.
3. Trouve une injection que le garde-fou ne détecte pas, ajoute-la à `tests/test_security.py`, puis corrige le motif.
