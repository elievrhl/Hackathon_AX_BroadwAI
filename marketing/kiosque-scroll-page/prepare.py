"""Prepare an isolated fictional edition for filming the unmodified frontend."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
THEMES=[
    ("Économie","01-economie",[
        "Comprendre les grandes transformations de l’économie",
        "Pourquoi les villes réinventent leurs commerces de proximité",
        "L’économie circulaire, de l’idée au quotidien",
        "Le temps long : une autre manière de penser l’innovation",
    ]),
    ("Sciences","02-sciences",[
        "Voyage aux frontières du système solaire",
        "Ce que les étoiles nous racontent sur nos origines",
        "Dans les coulisses des grandes découvertes scientifiques",
        "Observer l’invisible : les outils qui changent la recherche",
    ]),
    ("Culture & idées","03-culture",[
        "Quand l’art nous apprend à regarder autrement",
        "Ces œuvres qui font dialoguer les époques",
        "Pourquoi nous avons toujours besoin de raconter des histoires",
        "L’architecture, un langage pour habiter le monde",
    ]),
    ("Climat & vivant","04-planete",[
        "La biodiversité, cet équilibre qui nous relie",
        "À la rencontre des forêts que l’on ne voit pas",
        "Comment les océans façonnent notre planète",
        "Réapprendre à observer le vivant près de chez soi",
    ]),
    ("Tech & IA","05-technologies",[
        "L’intelligence artificielle à hauteur d’humain",
        "Les interfaces de demain se dessinent aujourd’hui",
        "Ce que le design peut changer dans notre vie numérique",
        "De l’idée au prototype : inventer des outils utiles",
    ]),
    ("Voyages & découvertes","06-voyage",[
        "Prendre les chemins de traverse en Méditerranée",
        "Voyager en train, et retrouver le plaisir du trajet",
        "La carte et le territoire : apprendre à se perdre",
        "À pied, les villes racontent une autre histoire",
    ]),
]
items=[]
images={}
for round_index in range(4):
    for theme_index,(section,art,titles) in enumerate(THEMES):
        num=len(items)+1
        ident=f"kiosque-demo-{num:02d}"
        # Two illustrated articles per subject, followed by short text cards.
        images[ident]=art if round_index<2 else None
        kind='video' if num in (2,9,17) else 'podcast' if num in (5,15) else 'article'
        items.append({
            'article_id':ident,'format':kind,'title':titles[round_index],
            'url':f'https://demo.kiosque.example/{ident}',
            'source':'Kiosque','published_at':'2026-09-27T08:00:00Z',
            'section':section,'role':'lead' if num==1 else 'secondary' if num in (2,3) else None,
            'selection_kind':'focused','reading_kind':'evergreen',
            'reading_time_minutes':4+(num%6) if kind=='article' else None,
            'media':{'duration_seconds':420+(num%5)*180,'channel_title':'Horizons','show_title':'Le temps de comprendre'} if kind!='article' else None,
            'brief':{'summary':f'Un regard accessible sur {section.lower()}, pour explorer de nouvelles idées et prendre le temps de comprendre.','key_points':[],'language':'fr','caveats':[]},
            'reason':'Un contenu de démonstration lié à vos centres d’intérêt.',
            'extraction_status':'extracted','image':{'alt':f'Illustration générée — {section}'},'image_checked':True,
        })
edition={'id':'kiosque-demo-diversite','user_id':'marketing-scroll-demo','title':'Le monde, au fil de vos curiosités.','created_at':'2026-09-27T08:00:00Z','status':'complete','items':items,'trace':[],'warnings':[],'usage':{},'diagnostics':{}}
(ROOT/'edition-demo.json').write_text(json.dumps(edition,ensure_ascii=False,indent=2))
(ROOT/'images-demo.json').write_text(json.dumps(images,ensure_ascii=False,indent=2))
print(f'Prepared {len(items)} fictional contents across {len(THEMES)} topics.')
