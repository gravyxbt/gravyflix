sub init()
    m.hero = m.top.FindNode("hero")
    m.rows = m.top.FindNode("rows")
    m.nav = m.top.FindNode("nav")
    m.statusPanel = m.top.FindNode("statusPanel")
    m.status = m.top.FindNode("status")
    m.notice = m.top.FindNode("notice")
    m.noticeTimer = m.top.FindNode("noticeTimer")
    m.hasMovies = false
    m.allRow = 0
    m.rows.ObserveField("focusedItem", "onMovieFocused")
    m.rows.ObserveField("selectedItem", "onMovieSelected")
    m.rows.ObserveField("exitUp", "focusHero")
    m.hero.ObserveField("playRequested", "onHeroPlay")
    m.hero.ObserveField("exitUp", "focusNavigation")
    m.hero.ObserveField("exitDown", "focusRows")
    m.nav.ObserveField("exitDown", "focusHero")
    m.nav.ObserveField("activated", "onNavigation")
    m.noticeTimer.ObserveField("fire", "clearNotice")
end sub

sub onMoviesChanged()
    movies = m.top.movies
    if movies = invalid then return
    definitions = BuildHomeRows(movies)
    root = CreateObject("roSGNode", "ContentNode")
    m.allRow = 0
    for each definition in definitions
        row = root.CreateChild("ContentNode")
        row.title = definition.title
        if definition.key = "all" then m.allRow = root.GetChildCount() - 1
        for each entry in definition.items
            item = row.CreateChild("MovieContent")
            item.SetFields({
                title: entry.title, description: entry.description
                metadataLine: entry.metadataLine, cardImage: entry.cardImage
                portraitArt: entry.portraitArt, heroImage: entry.heroImage
                progress: entry.progress, movieData: entry.movieData, homeRowKey: definition.key
            })
        end for
    end for
    m.hasMovies = root.GetChildCount() > 0
    m.rows.content = root
    if m.hasMovies
        m.hero.content = root.GetChild(0).GetChild(0)
        m.top.statusText = ""
        onStatus()
        m.rows.CallFunc("jumpToRow", 0)
    else
        m.top.statusText = "No movies yet." + Chr(10) + "Add movies to your library, scan it, then press OK to refresh."
    end if
end sub

sub onStatus()
    showingStatus = m.top.statusText <> ""
    m.statusPanel.visible = showingStatus
    m.status.text = m.top.statusText
    m.hero.visible = not showingStatus and m.hasMovies
    m.rows.visible = not showingStatus and m.hasMovies
    if showingStatus then m.top.SetFocus(true)
end sub

sub focusHome()
    if m.hasMovies and m.top.statusText = ""
        focusRows()
    else
        m.top.SetFocus(true)
    end if
end sub

sub focusRows()
    if m.hasMovies and m.top.statusText = "" then m.rows.CallFunc("focusList")
end sub

sub focusHero()
    if m.hasMovies and m.top.statusText = "" then m.hero.SetFocus(true)
end sub

sub focusNavigation()
    m.nav.SetFocus(true)
end sub

sub onMovieFocused()
    item = m.rows.focusedItem
    if item <> invalid then m.hero.content = item
end sub

sub onMovieSelected()
    item = m.rows.selectedItem
    if item = invalid then return
    if item.homeRowKey = "continue" and HomeResumeTarget(item.movieData) <> invalid
        m.top.playMovie = item.movieData
    else
        m.top.selectedMovie = item.movieData
    end if
end sub

sub onHeroPlay()
    if m.hero.content <> invalid then m.top.playMovie = m.hero.content.movieData
end sub

sub onNavigation()
    if m.top.statusText <> "" then return
    if m.nav.activated = "movies"
        m.rows.CallFunc("jumpToRow", m.allRow)
    else if m.nav.activated = "home"
        m.rows.CallFunc("jumpToRow", 0)
    else if m.nav.activated = "search"
        m.notice.text = "Search is coming later. Choose Movies to browse your library."
        m.noticeTimer.control = "stop"
        m.noticeTimer.control = "start"
    end if
end sub

sub clearNotice()
    m.notice.text = ""
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "options" or (key = "OK" and m.top.statusText <> "")
        m.top.refreshRequested++
        return true
    end if
    ' Back always bubbles to MainScene, which preserves the existing exit behavior.
    return false
end function
