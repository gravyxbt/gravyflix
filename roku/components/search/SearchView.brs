sub init()
    m.grid = m.top.FindNode("results")
    m.delay = m.top.FindNode("queryDelay")
    m.layoutDelay = m.top.FindNode("keyboardLayoutDelay")
    m.layoutDelay.ObserveField("fire", "fitKeyboard")
    m.layoutAttempts = 0
    m.actionFocus = m.top.FindNode("actionFocus")
    m.index = []
    m.zone = "keyboard"
    m.actionIndex = 0
    m.rebuilding = false
    m.keyboard = CreateObject("roSGNode", "DynamicMiniKeyboard")
    if m.keyboard = invalid then m.keyboard = CreateObject("roSGNode", "MiniKeyboard")
    m.keyboard.scale = [0.78, 0.78]
    m.top.FindNode("keyboardHost").AppendChild(m.keyboard)
    if m.keyboard.HasField("domain") then m.keyboard.domain = "generic"
    if m.keyboard.textEditBox <> invalid
        if m.keyboard.textEditBox.HasField("maxTextLength") then m.keyboard.textEditBox.maxTextLength = 75
    end if
    if m.keyboard.HasField("keyGrid")
        if m.keyboard.keyGrid.HasField("horizWrapping") then m.keyboard.keyGrid.horizWrapping = false
    end if
    m.keyboard.ObserveField("text", "onQueryChanged")
    m.delay.ObserveField("fire", "applyQuery")
    m.grid.ObserveField("itemFocused", "onResultFocused")
    m.grid.ObserveField("itemSelected", "onResultSelected")
    m.top.FindNode("empty").text = "Start typing to find something to watch."
end sub

sub onLibraryChanged()
    if m.top.movies = invalid then return
    m.index = BuildSearchIndex(m.top.movies)
    applyQuery()
end sub

sub onQueryChanged()
    m.delay.control = "stop"
    m.delay.control = "start"
end sub

function resultAt(index as integer) as dynamic
    if m.grid.content = invalid or index < 0 then return invalid
    return m.grid.content.GetChild(index)
end function

sub applyQuery()
    m.delay.control = "stop"
    selected = resultAt(m.grid.itemFocused)
    selectedKey = ""
    if selected <> invalid then selectedKey = SearchItemKey(selected.movieData)
    matches = FindSearchMatches(m.index, m.keyboard.text)
    root = CreateObject("roSGNode", "ContentNode")
    position = 0
    for each movie in matches.items
        entry = MoviePresentation(movie)
        item = root.CreateChild("MovieContent")
        item.SetFields({title:entry.title,description:entry.description,metadataLine:entry.metadataLine,
            cardImage:entry.cardImage,portraitArt:entry.portraitArt,heroImage:entry.heroImage,
            progress:entry.progress,movieData:movie,homeRowKey:"search"})
        if SearchItemKey(movie) = selectedKey then position = root.GetChildCount() - 1
    end for
    m.rebuilding = true
    m.grid.content = root
    m.grid.visible = root.GetChildCount() > 0
    m.top.FindNode("empty").visible = not m.grid.visible
    if matches.normalized = ""
        m.top.FindNode("resultCount").text = ""
        m.top.FindNode("empty").text = "Start typing to find something to watch."
    else if matches.total = 0
        m.top.FindNode("resultCount").text = "No results"
        m.top.FindNode("empty").text = "No titles match your search." + Chr(10) + "Try a shorter title, actor name or genre."
    else
        count = matches.total.ToStr() + " results"
        if matches.total = 1 then count = "1 result"
        if matches.total > matches.items.Count() then count = "First " + matches.items.Count().ToStr() + " of " + matches.total.ToStr() + " · Refine your search"
        m.top.FindNode("resultCount").text = count
        m.grid.jumpToItem = position
    end if
    m.rebuilding = false
    onResultFocused()
    if not m.grid.visible and m.zone = "results" then focusKeyboard()
end sub

sub onResultFocused()
    item = resultAt(m.grid.itemFocused)
    text = ""
    if item <> invalid then text = item.title + "  ·  " + item.metadataLine
    m.top.FindNode("preview").text = text
end sub

sub onResultSelected()
    if m.rebuilding or not m.grid.HasFocus() then return
    item = resultAt(m.grid.itemSelected)
    if item = invalid then return
    m.top.selectedMovie = item.movieData
    m.top.titleRequested++
end sub

sub focusSearch()
    if m.zone = "results" and m.grid.visible
        focusResults(false)
    else
        focusKeyboard()
    end if
end sub

sub focusKeyboard()
    m.zone = "keyboard"
    m.actionFocus.visible = false
    m.keyboard.SetFocus(true)
    m.layoutAttempts = 0
    m.layoutDelay.control = "start"
end sub

sub focusResults(flush = true as boolean)
    if flush then applyQuery()
    if not m.grid.visible then return
    m.zone = "results"
    m.actionFocus.visible = false
    m.grid.SetFocus(true)
end sub

sub focusActions()
    m.zone = "actions"
    m.top.SetFocus(true)
    m.actionFocus.visible = true
    m.actionFocus.translation = [m.actionIndex * 238, 0]
end sub

sub clearQuery()
    m.keyboard.text = ""
    applyQuery()
    focusKeyboard()
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "play"
        focusResults()
        return true
    end if
    if m.zone = "results"
        if key = "back" or key = "left" or key = "up"
            focusKeyboard()
            return true
        end if
    else if m.zone = "actions"
        if key = "left" or key = "right"
            m.actionIndex = 0
            if key = "right" then m.actionIndex = 1
            focusActions()
        else if key = "OK"
            if m.actionIndex = 0 then focusResults() else clearQuery()
        else if key = "up" or key = "back"
            focusKeyboard()
        else if key = "down"
            focusResults()
        else
            return false
        end if
        return true
    else
        ' Keyboard consumes its own letter navigation; only boundary keys bubble.
        if key = "right"
            focusResults()
        else if key = "down"
            focusActions()
        else if key = "up"
            m.top.exitUp++
        else if key = "back"
            m.top.exitRequested++
        else
            return false
        end if
        return true
    end if
    return false
end function

sub updateCachedMovies(movies as object)
    m.index = BuildSearchIndex(movies)
    if m.grid.content = invalid then return
    byId = {}
    for each movie in movies
        byId[SearchItemKey(movie)] = movie
    end for
    m.rebuilding = true
    for i = 0 to m.grid.content.GetChildCount() - 1
        item = m.grid.content.GetChild(i)
        key = SearchItemKey(item.movieData)
        if byId.DoesExist(key)
            movie = byId[key]
            item.movieData = movie
            item.progress = MoviePresentation(movie).progress
        end if
    end for
    m.rebuilding = false
    onResultFocused()
end sub

sub fitKeyboard()
    ' Native textures can finish constructing after init; bounded retries measure
    ' their final footprint instead of treating the widget as a fixed-size image.
    placement = SearchKeyboardPlacement(m.keyboard.localBoundingRect())
    if placement <> invalid
        m.keyboard.scale = [placement.scale, placement.scale]
        m.keyboard.translation = placement.translation
    end if
    m.layoutAttempts++
    if m.layoutAttempts >= 8 then m.layoutDelay.control = "stop"
end sub
