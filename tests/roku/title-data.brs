sub Main()
    movie = {description:"A story about a family.",cast:["Star One","Star Two"]}
    check(TitleSummary(movie) = "A story about a family.", "Movie synopsis is presented")
    check(TitleCast(movie) = "Starring: Star One, Star Two", "Short principal cast list")
    check(TitleSummary({}) = "Summary not available yet.", "Missing data has a friendly fallback")
    check(TitleCast({}) = "", "No invented cast for missing metadata")
    check(TitleSummary({kind:"episode",description:"Series story",description_scope:"series"}) = "Series overview: Series story", "Fallback is not misrepresented as an episode summary")
    check(TitleCast({kind:"episode",cast_scope:"series",cast:["Star"]}) = "Series cast: Star", "Episode uses an honest series cast label")
    check(Len(TitleSummary(movie, 15)) <= 16, "Long synopsis is bounded for TV layout")
    print "PASS: Title page presentation"
end sub
sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub
