sub Main()
    library = [
        {id:1,kind:"movie",title:"Iron Man",genres:["Action","Science Fiction"],cast:["Robert Downey Jr."]},
        {id:2,kind:"movie",title:"Iron Man 2",genres:["Action"],cast:["Robert Downey Jr."]},
        {id:"show-office",kind:"show",title:"The Office",genres:["Comedy"],cast:["Steve Carell","John Krasinski"]},
        {id:3,kind:"movie",title:"Deadpool",genres:["Action","Comedy"],cast:["Ryan Reynolds"]},
        {id:4,kind:"movie",title:"Café Society",genres:["Romance"]},
        {id:5,kind:"movie",title:"Chappelle's Show: A Special",genres:[]},
        {id:99,kind:"episode",title:"The Office Episode 1"}
    ]
    index = BuildSearchIndex(library)
    check(index.Count() = 6, "Only top-level movies and series are indexed")
    hits = FindSearchMatches(index,"IRON MAN")
    check(hits.total = 2 and hits.items[0].id = 1, "Case-insensitive exact title ranks first")
    check(FindSearchMatches(index,"REYNOLDS").items[0].id = 3, "Actor surname search")
    check(FindSearchMatches(index,"john krasinski").items[0].id = "show-office", "Series actor search")
    check(FindSearchMatches(index,"science fiction").items[0].id = 1, "Multiword genre search")
    check(FindSearchMatches(index,"ryan comedy").items[0].id = 3, "All query terms can match cast and genre")
    check(FindSearchMatches(index,"cafe").items[0].id = 4, "Accent folding")
    check(FindSearchMatches(index,"chappelles").items[0].id = 5, "Apostrophe folding")
    check(SearchNormalize("  Rick & Morty  ") = "rick and morty", "Punctuation and whitespace normalization")
    check(FindSearchMatches(index,"").total = 0, "Empty query is an invitation to type")
    check(FindSearchMatches(index,"wrongtitle").total = 0, "No-match result")
    limited = FindSearchMatches(index,"action",1)
    check(limited.total = 3 and limited.items.Count() = 1, "Result cap retains total count")
    check(BuildSearchIndex([library[0],library[0]]).Count() = 1, "Duplicate IDs are not duplicated")
    check(BuildSearchIndex([{id:8,title:"Bare movie",cast:"bad",genres:invalid}]).Count() = 1, "Incomplete metadata is safe")
    print "PASS: Search data matching"
end sub
sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub
