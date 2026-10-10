sub Main()
    rows = BuildHomeRows([])
    check(rows.Count() = 0, "Empty library has no shelves")
    basic = MoviePresentation({title: "Unknown"})
    check(basic.metadataLine = "", "Missing metadata stays absent")
    check(basic.description = "", "No invented description")
    check(basic.cardImage = "pkg:/images/card-fallback.png", "Local card fallback")
    check(basic.heroImage = "pkg:/images/hero-fallback.png", "Local hero fallback")
    check(RuntimeLabel(7680) = "2h 8m", "Runtime seconds formatted")
    check(RuntimeLabel(59) = "", "No misleading zero-minute runtime")
    metadata = MoviePresentation({title:"Test", year:2024, duration:7680, overview:"Description", backdrop_url:"http://image/back.jpg", poster_url:"http://image/poster.jpg"})
    check(metadata.metadataLine = "2024  ·  2h 8m", "Year and runtime")
    check(metadata.description = "Description", "Overview alias")
    check(metadata.cardImage = "http://image/back.jpg", "Landscape before portrait")
    portrait = MoviePresentation({title:"Portrait",poster_url:"http://image/poster.jpg"})
    check(portrait.portraitArt, "Portrait keeps its aspect ratio")
    check(portrait.heroImage = "pkg:/images/hero-fallback.png", "Portrait not stretched into hero")
    rows = BuildHomeRows([
        {id:1,title:"Zulu",date_added:"2025-01-01"}
        {id:2,title:"alpha",date_added:"2026-01-01",duration:3600,resume_position:120}
        {id:3,title:"Bravo",date_added:"2024-01-01",duration:3600,resume_position:3590}
        {id:4,title:"Completed",date_added:"2023-01-01",duration:3600,resume_position:500,completed:true}
    ])
    check(rows.Count() = 4, "Base shelves plus uncategorized when progress exists")
    check(rows[0].key = "continue", "Continue first")
    check(rows[0].items.Count() = 1, "Exclude finished and near-complete")
    check(rows[0].items[0].movieData.id = 2, "Original identity retained")
    check(rows[1].items[0].movieData.id = 2, "Recent sorted newest first")
    check(rows[2].items[0].title = "alpha", "All movies sorted case-insensitively")
    check(rows[2].items[3].title = "Zulu", "All movies sort end")
    many = []
    for i = 1 to 40
        many.Push({id:i,title:"Movie "+i.ToStr()})
    end for
    rows = BuildHomeRows(many)
    check(rows.Count() = 3, "No fake Continue shelf; uncategorized included")
    check(rows[0].items.Count() = 24, "Recent shelf bounded")
    check(rows[1].items.Count() = 40, "All movies not truncated")
    rows = BuildHomeRows([
        {id:"show-test",kind:"show",title:"A Show",season_count:2,episode_count:15,date_added:"2026-01-02"}
        {id:9,kind:"movie",title:"A Movie",date_added:"2026-01-01"}
    ])
    check(rows.Count() = 4, "Recent, shows, movies and uncategorized shelves")
    check(rows[0].items.Count() = 2, "Recent has one card per title")
    check(rows[1].key = "shows", "TV Shows shelf")
    check(rows[1].items[0].metadataLine = "2 seasons  ·  15 episodes", "Show counts in hero")
    check(rows[2].items.Count() = 1, "Show excluded from All Movies")
    rows = BuildHomeRows([{id:"show-only",kind:"show",title:"Only Show",season_count:1,episode_count:1}])
    check(rows.Count() = 3, "Show-only libraries have no empty movie row")
    categories = BuildHomeRows([
        {id:1,title:"Zulu",genres:["Action","Science Fiction","Action"]}
        {id:"show-1",kind:"show",title:"A Show",genres:["Comedy","Action"],season_count:1,episode_count:2}
        {id:2,title:"Unknown",genres:[]}
    ])
    check(categories.Count() = 7, "Base shelves, three genres and uncategorized")
    check(categories[3].title = "Action", "Genre shelves sort alphabetically")
    check(categories[3].items.Count() = 2, "Duplicate genre tag does not duplicate movie")
    check(categories[3].items[0].movieData.id = "show-1", "Shows and movies share genre shelves with identity intact")
    check(categories[4].title = "Comedy", "Comedy category follows Action")
    check(categories[5].title = "Science Fiction", "Science Fiction category exists")
    check(categories[6].items[0].movieData.id = 2, "Unknown genre goes to Uncategorized")
    malformed = BuildHomeRows([{id:9,title:"Broken",genres:"Comedy"}])
    check(malformed[2].title = "Uncategorized", "Invalid genres do not crash library")
    print "PASS: Home data adapter"
end sub

sub check(condition as boolean, message as string)
    if not condition
        print "FAIL: "; message
        stop
    end if
end sub
