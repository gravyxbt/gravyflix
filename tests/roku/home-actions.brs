sub Main()
    episode = {id:42,kind:"episode",season_number:2,episode_number:3,resume_position:125,duration:1300}
    show = {id:"show-test",kind:"show",resume_episode:episode}
    check(HomeResumeTarget(show).id = 42, "Series resume resolves to the exact episode")
    check(HomeActionLabel(show) = "▶  Resume", "Series hero says Resume")
    check(HomeActionLabel({kind:"show"}) = "Episodes", "Unwatched series opens its browser")
    check(HomeResumeTarget({kind:"show"}) = invalid, "No fabricated episode when progress is missing")
    check(HomeActionLabel({id:9,resume_position:120,duration:3600}) = "▶  Resume", "Movie resume action")
    check(HomeActionLabel({id:9}) = "▶  Play", "Unwatched movie action")
    check(HomeResumeTarget({kind:"show",resume_episode:{id:3,season_number:0,resume_position:120}}) = invalid, "Extras cannot be the series resume target")
    check(HomeResumeTarget({id:4,resume_position:125,duration:1300,completed:true}) = invalid, "Completed item is not resumable")
    check(HomeResumeTarget({id:4,resume_position:1290,duration:1300}) = invalid, "Near-complete item is not resumable")
    m.rows = {selectedItem:{homeRowKey:"continue",movieData:show}}
    m.top = {}
    onMovieSelected()
    check(m.top.playMovie.resume_episode.id = 42, "Continue Watching OK publishes direct playback")
    check(m.top.selectedMovie = invalid, "Continue Watching bypasses season selection")
    m.rows.selectedItem.homeRowKey = "shows"
    m.top = {}
    onMovieSelected()
    check(m.top.selectedMovie.kind = "show", "TV Shows shelf keeps normal season browsing")
    check(m.top.playMovie = invalid, "Normal browsing does not autoplay")
    m.rows.selectedItem = {homeRowKey:"continue",movieData:{kind:"show"}}
    m.top = {}
    onMovieSelected()
    check(m.top.selectedMovie.kind = "show", "Missing resume data falls back safely to browsing")
    print "PASS: Home resume actions"
end sub

sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub
