# readonly-sql-mcp — en bref

Un serveur [MCP](https://modelcontextprotocol.io) qui permet à un agent IA
d'interroger une base SQL, en garantissant qu'il ne peut que **lire**.

*La documentation complète est en anglais : [README.md](README.md). Ce
résumé ne la remplace pas.*

**Le problème.** Dire à un agent « n'utilise que SELECT », c'est une consigne,
pas une garantie : elle peut être oubliée, mal lue, ou contredite par un texte
que l'agent lit en chemin.

**La réponse : trois verrous indépendants**, chacun testé seul, comme si les
deux autres étaient cassés.

1. **La base refuse de changer.** C'est SQLite lui-même qui l'impose : connexion
   en lecture seule, plus une liste blanche qui n'autorise que la lecture.
   Trouvé en l'attaquant : la lecture seule ne couvrait que le fichier
   principal, et `ATTACH` atteignait n'importe quel autre fichier du disque.
2. **Une seule requête de lecture.** Un vrai analyseur SQL, jamais une regex.
   Trouvé en l'attaquant : une liste des instructions « dangereuses » laissait
   passer `ANALYZE`, `REINDEX` et `LOAD DATA`. Seule la liste blanche les arrête.
3. **Ni trop gros, ni trop long.** Plafond de lignes, minuteur, taille maximale
   d'une valeur, tous appliqués par la base pendant que la requête tourne.

**La preuve.** `pytest` vérifie chaque verrou ; `python tools/mutation_check.py`
casse chaque protection exprès et exige qu'un test passe au rouge.

**Les évaluations.** Un vrai agent, avec ces trois outils et rien d'autre,
répond à des questions dont la réponse exacte est calculée d'avance, et une
note piégée dans la base essaie de lui faire effacer les factures. Le banc est
prêt et testé ; les résultats de la première campagne ne sont pas encore
publiés.
