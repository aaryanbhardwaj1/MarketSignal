"""Phrase pools for synthetic survey verbatims and product reviews.

Fictional data created for the MarketSignal demo. Combined deterministically by
tabular.py with a seeded random.Random so that rows read as varied free text.
"""

SURVEY_CORE = {
    "fit_inconsistency": [
        "Every Northstar item I own fits a little differently even when the tag says the same size.",
        "The same size in two colors of the same legging did not fit the same.",
        "I never know if I am a small or a medium with you until it arrives.",
        "My last two orders in the same size felt like they came from different brands.",
        "The waist on the joggers is generous but the length is short, so nothing quite works.",
        "Fit changes between seasons, so I cannot just reorder what I liked.",
        "Tops run boxy and the shorts run tight, which makes building an outfit annoying.",
        "I wish your fit notes on the site actually matched how things fit in real life.",
        "Half my returns are because the fit was off, not because I disliked the style.",
        "The new batch of sports bras fits tighter than the old ones in the same size.",
    ],
    "sizing_across_categories": [
        "My shoe size in your running line is not my size in your court shoes.",
        "I wear different sizes in your tops and bottoms, and the size chart does not explain why.",
        "Your size chart is one table for everything, but apparel and footwear clearly use different patterns.",
        "Buying a full outfit means guessing three different sizes.",
        "I had to size up in the trail shoe but down in the trainer, which makes no sense to me.",
        "A simple size converter between your categories would save me a return every time.",
        "Hoodies and joggers from the same collection fit like they were cut for different people.",
        "I trust the shoe sizing but the apparel sizing is a coin flip.",
    ],
    "knit_upper_durability": [
        "The knit upper started to fray near the toe within a couple of months.",
        "My runners look worn out long before the sole does.",
        "The mesh tore at the flex point and I only use them for the gym and walking.",
        "Great comfort out of the box but the upper did not hold up to daily wear.",
        "I expected the knit to last at least a season and it did not.",
        "There is a small hole forming where my big toe bends after about ten weeks.",
        "The fabric pilled after a few washes, which is not great at this price.",
        "Support offered a discount instead of a replacement when the upper wore through.",
    ],
    "price_vs_value": [
        "Prices went up but the quality did not, so the value is not there anymore.",
        "I only buy during sales now because full price feels too high.",
        "Similar leggings from the value brands are half the price and almost as good.",
        "If I am paying premium prices I want them to last longer than a semester.",
        "The basics are fairly priced but the footwear feels expensive for what it is.",
        "I compare prices on my phone in the store and usually buy elsewhere.",
        "Shipping fees on small orders make the total feel like a bad deal.",
        "A loyalty discount for students would make a real difference for me.",
    ],
    "sustainability_transparency": [
        "I want to know what the shoes are made of and where, not just a green label.",
        "The recycled claims are vague and I cannot find any details on the product page.",
        "Tell me the actual percentage of recycled material instead of saying eco friendly.",
        "I would pick the brand that is honest about its factories, even if it costs a bit more.",
        "There is no information about repair or recycling old pairs.",
        "Packaging is excessive for a single pair of socks.",
        "I looked for a sustainability report and could not find anything recent.",
    ],
    "delivery_speed": [
        "Delivery took over a week, which is slow compared with other sites I use.",
        "I ordered for a race weekend and the package arrived after the race.",
        "The tracking page was not updated for four days.",
        "Free shipping is great but not if it takes ten days.",
        "I would pay a little extra for two day delivery if it was offered.",
        "In store pickup would help because I live near a mall with your store.",
        "The order was split into three packages arriving on different days.",
    ],
    "lack_of_personalization": [
        "I would love to customize colors or add my initials like I can with other brands.",
        "Everything looks the same as what everyone else is wearing.",
        "A way to save my fit preferences and get recommendations would be nice.",
        "My team wanted matching custom shoes and there was no option for it.",
        "I would try a made for me option if it did not take forever.",
        "The site recommends things that have nothing to do with what I bought.",
    ],
    "community_social_proof": [
        "I rarely see your products in my feed or from creators I follow.",
        "There are not many reviews with photos, so it is hard to judge fit.",
        "My run club mostly wears other brands, so I hear less about yours.",
        "I would join group runs or events if you hosted any near me.",
        "Real customer try on videos would help more than polished ads.",
        "None of my friends talk about the brand, which makes me hesitate.",
    ],
}

SURVEY_TAIL_POSITIVE = [
    "Still my go to brand for training.",
    "Overall I am happy and will keep buying.",
    "The leggings are still the best I own.",
    "Customer service was friendly when I reached out.",
    "Love the colors this season.",
    "I recommend you to friends anyway.",
]
SURVEY_TAIL_NEUTRAL = [
    "Not a dealbreaker, but it adds up.",
    "Fix that and I would buy more often.",
    "It is fine, just not special.",
    "I keep coming back mostly out of habit.",
    "Hoping the next drop is better.",
]
SURVEY_TAIL_NEGATIVE = [
    "I have started buying from other brands.",
    "Honestly I am close to giving up on the brand.",
    "It feels like nobody is listening.",
    "That experience really put me off.",
    "I will think twice before ordering again.",
]

REVIEW_POSITIVE = [
    "Comfortable from the first wear and true to size.",
    "Great cushioning for daily runs, my knees feel better.",
    "The fabric feels soft and does not ride up.",
    "Looks even better in person than on the site.",
    "Light, breathable and easy to style outside the gym.",
    "Fits exactly like my last pair, which I appreciate.",
    "Held up well through a full training block.",
    "Pockets are deep enough for my phone, finally.",
    "Washes well and the color has not faded.",
    "Good grip on wet pavement and gym floors.",
]
REVIEW_NEGATIVE = [
    "Runs about half a size small, had to exchange.",
    "The stitching came loose after a few weeks.",
    "Sizing is different from the other pair I bought from the same brand.",
    "Took nine days to arrive and the box was damaged.",
    "Too expensive for how quickly it wore out.",
    "The upper started pilling and fraying near the toe.",
    "Waistband rolls down during squats.",
    "Color was much duller than the photos.",
    "Narrow toe box, my feet hurt after an hour.",
    "Return process was slow and the refund took two weeks.",
]
REVIEW_MIXED = [
    "Nice design but the fit is inconsistent with the size chart.",
    "Comfortable, though I wish there were more color options.",
    "Good value on sale, would not pay full price.",
    "Decent for the gym, not great for longer runs.",
    "Love the feel, but sustainability info on the tag is vague.",
    "Solid shoe, but delivery took longer than promised.",
]
REVIEW_CLOSERS = [
    "Would buy again.",
    "Ordering another color.",
    "Probably will not repurchase.",
    "Three stars feels fair.",
    "Recommended for casual use.",
    "Hope the next version fixes this.",
    "My friends asked where I got them.",
    "",
    "",
    "",
]
REVIEW_CUSTOM = [
    "The custom colorway turned out exactly like the preview.",
    "Adding my initials made it feel special, great gift idea.",
    "Custom order took almost two weeks, which was longer than I wanted.",
    "Love that I could pick team colors for our squad.",
    "Fun customizer but the extra cost is hard to justify.",
]

SP_SURVEY_CORE = {
    "fit_inconsistency": [
        "My boots and trail runners from Southpeak are not the same size at all.",
        "The shell fits fine in the shoulders but the sleeves are short.",
        "Every season the fit of the hiking pants seems to change.",
        "I had to exchange my boots twice to get the right size.",
    ],
    "waterproofing": [
        "The jacket wetted out after an hour of steady rain.",
        "My boots stopped being waterproof after one season.",
        "The rain pants leak at the seams near the knees.",
    ],
    "durability": [
        "The pack zipper broke on my second trip.",
        "Sole started peeling away on the trail after a few months.",
        "Fabric on the fleece pilled quickly.",
    ],
    "price_vs_value": [
        "Good gear but the prices keep creeping up.",
        "I wait for the end of season sale before buying anything.",
        "Hard to justify the price compared with outfitter house brands.",
    ],
    "sustainability_transparency": [
        "I want to know which fabrics are recycled and where they are made.",
        "A repair program would make me much more loyal.",
        "The sustainability page is mostly photos and slogans.",
    ],
    "delivery_speed": [
        "My order took eight days to reach me before a trip.",
        "Shipping to rural areas is slow and tracking is unreliable.",
        "I would pay for faster delivery before a big trip.",
    ],
    "personalization": [
        "I would like custom patches or embroidery for my scout troop.",
        "A fit profile that remembers my sizes would help.",
    ],
    "community": [
        "I would come to more group hikes and trail cleanups if they were near me.",
        "Hard to find real customer photos of the gear on the trail.",
        "My hiking group mostly wears other labels, so I hear less about Southpeak.",
    ],
    "weight": [
        "The tent is heavier than the listing suggests.",
        "I want lighter packs for longer hikes.",
    ],
}
SP_SURVEY_TAILS = [
    "Still love the brand overall.",
    "Would recommend with that caveat.",
    "Considering switching brands.",
    "Customer service did help in the end.",
    "",
    "",
]

SURVEY_CONTEXT = [
    "I mostly shop on the app.",
    "I buy for the gym and for class.",
    "I run four days a week.",
    "I shop with you about every couple of months.",
    "I mainly buy leggings and tees.",
    "I started buying Northstar in college.",
    "I usually order online and return in store.",
    "I play club volleyball and train most days.",
    "My budget is tight so I compare a lot.",
    "I buy for hiking and weekend runs.",
    "I usually shop the sale section first.",
    "I discovered the brand through friends.",
    "Most of my wardrobe is athletic wear.",
    "I take studio classes three times a week.",
]
REVIEW_CONTEXT = [
    "Bought these for marathon training.",
    "Wear them to class almost every day.",
    "Got these as a birthday gift.",
    "Second pair from this line.",
    "Using them mostly for lifting and HIIT.",
    "Ordered my usual size.",
    "Update after a month of wear.",
    "Bought on sale.",
    "Picked these up in store after trying them on.",
    "First time buying from this brand.",
    "I walk a lot on campus.",
    "Wearing these for studio classes.",
    "",
    "",
]
