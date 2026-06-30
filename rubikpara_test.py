import re
import json

with open('rubikpara_html.txt') as f:
    html = f.read()

# The RSC contains: \"card\":{\"id\":1,\"category\":\"Ev & Dekorasyon\",\"brand\":\"English Home\",\"title\":\"English Home&apos;da %8 Anında Cashback\",\"src\":\"/images/campaings/english-home.png\",\"logo\":\"https://...\",\"content\":...}
matches = re.findall(r'\\\"card\\\":(\{\\\"id\\\".*?\\\"logo\\\":\\\"[^\"]+\\\")', html)
for i, m in enumerate(matches):
    try:
        # It's double escaped in the file! Wait, the file is just text. Let's try raw regex
        pass
    except Exception as e:
        pass

# Actually, the file contains: "card":{"id":1,"brand":"English Home","category":"Ev & Dekorasyon","title":"English Home&apos;da %8 Anında Cashback","src":"/images/campaings/english-home.png","logo":"https://giftcheckbucket.alisverislio.net/fe2d6dec-87eb-4bca-ba05-0ae6beaa495c.png","content":["$","div",null,{"className":"space-y-6","children":[["$","div",null,{"className":"flex items-center gap-4","children":[["$","div",null,{"className":"h-16 w-16 rounded-full bg-orange-600 flex items-center justify-center overflow-hidden","children":["$","$La",null,{"src":"https://giftcheckbucket.alisverislio.net/fe2d6dec-87eb-4bca-ba05-0ae6beaa495c.png","alt":"English Home","width":64,"height":64,"className":"w-full h-full object-contain"}]}],["$","div",null,{"children":[["$","h3",null,{"className":"text-2xl font-bold text-gray-800","children":"English Home"}],"$Lb"]}]]}],"$Lc","$Ld"]}]}
# So I can just match '"card":{...'
cards = re.findall(r'\"card\":(\{\"id\":\d+,\".*?\"logo\":\"[^\"]+\")', html)
print("Found cards:", len(cards))
for c in cards:
    print(c)

# What about the details?
# They are in: b:["$","p",null,{"className":"text-lg text-gray-600","children":"Anında %8 cashback"}]
# and: c:["$","p",null,{"className":"text-gray-700 leading-relaxed","children":"English Home'da Rubikpara..."}]
details = re.findall(r'\"className\":\"text-gray-700 leading-relaxed\",\"children\":\"(.*?)\"', html)
print("Found details:", len(details))
for d in details:
    print(d)

