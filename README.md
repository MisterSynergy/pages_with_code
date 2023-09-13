# Pages with code
This is a Wikidata bot that periodically updates a list of community-maintained wikipages with sourcecode (excluding pages in Template and User namespace).

Currently, the report can be read at [User:MisterSynergy/pages_with_code](https://www.wikidata.org/wiki/User:MisterSynergy/pages_with_code).

## Technical requirements
The bot is currently scheduled to run weekly on [Toolforge](https://wikitech.wikimedia.org/wiki/Portal:Toolforge) from within the `msynbot` tool account. It depends on the [shared pywikibot files](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Pywikibot#Using_the_shared_Pywikibot_files_(recommended_setup)) and is running in a Kubernetes environment using Python 3.11.2.
