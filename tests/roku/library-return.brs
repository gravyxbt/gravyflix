sub Main()
    m.top = {FindNode:findRestart}
    m.library = {ObserveField:recordObserver,observed:{},visible:false, CallFunc:recordFocus, sentinel:"original rows"}
    m.showBrowser = {ObserveField:recordObserver,observed:{},visible:true, CallFunc:recordFocus}
    m.details = {visible:false}
    observeTitleActions()
    check(m.library.observed.DoesExist("titleRequested") and m.library.observed.DoesExist("playRequested"), "Title navigation observes command counters")
    check(not m.library.observed.DoesExist("selectedMovie") and not m.library.observed.DoesExist("playMovie"), "Mutable library payloads never trigger navigation")
    check(m.showBrowser.observed.DoesExist("episodeRequested") and not m.showBrowser.observed.DoesExist("selectedEpisode"), "Episode navigation also requires an explicit command")
    m.mode = "show"
    m.loading = true
    check(onKeyEvent("back", true), "Back from series is handled")
    check(m.mode = "library" and m.library.visible, "Series returns to library")
    check(m.task = invalid, "Returning preserves the library while an update is already pending")
    check(m.library.called = "focusHome", "Existing library receives focus")
    check(not m.showBrowser.visible, "Series browser is hidden")
    m.mode = "details"
    m.fromShow = false
    m.details.visible = true
    check(onKeyEvent("back", true), "Back from movie is handled")
    check(m.mode = "library" and not m.details.visible, "Movie returns to library")
    check(m.task = invalid, "Movie Back also retains existing library")
    m.mode = "details"
    m.fromShow = true
    check(onKeyEvent("back", true), "Episode Back is handled")
    check(m.mode = "show" and m.showBrowser.called = "focusEpisodes", "Episode returns to existing episode browser")
    check(onKeyEvent("back", true), "Series Back remains usable")
    m.preserveLibrary = true
    m.library.movies = ["unchanged shelves"]
    m.task = {result:{movies:[{id:5,title:"Updated progress"}]}}
    onMovies()
    check(m.library.called = "updateCachedMovies", "Background response patches existing nodes")
    check(m.library.movies[0] = "unchanged shelves", "Background response does not replace library content")
    m.library.statusText = ""
    m.task.result = {error:"offline"}
    onMovies()
    check(m.library.statusText = "", "Background error does not hide the usable library")
    m.mode = "details"
    onSelected()
    onHeroPlay()
    onEpisodeSelected()
    check(m.mode = "details", "Stale actions from hidden browsers cannot change screens")
    print "PASS: Library return navigation"
end sub
sub recordFocus(name as string, value = invalid as dynamic)
    m.called = name
end sub
sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub

function findRestart(id as string) as object
    return {visible:false}
end function

sub recordObserver(field as string, callback as string)
    m.observed[field] = callback
end sub
