sub init()
    m.tile = m.top.FindNode("tile")
    m.art = m.top.FindNode("art")
    m.title = m.top.FindNode("title")
    m.ring = m.top.FindNode("ring")
    m.progress = m.top.FindNode("progress")
    m.played = m.top.FindNode("played")
end sub

sub onContent()
    content = m.top.itemContent
    if content = invalid then return
    m.title.text = content.title
    if content.portraitArt
        m.art.loadDisplayMode = "scaleToFit"
    else
        m.art.loadDisplayMode = "scaleToZoom"
    end if
    m.art.uri = content.cardImage
    m.progress.visible = content.progress > 0 and content.progress < 1
    m.played.width = 184 * content.progress
end sub

sub onFocus()
    ' Use the RowList's interpolated focus clock; no per-card timers or network work.
    amount = m.top.focusPercent * m.top.rowFocusPercent
    if not m.top.rowListHasFocus then amount = 0
    if m.top.gridHasFocus then amount = m.top.focusPercent
    size = 1.0 + 0.07 * amount
    m.tile.scale = [size, size]
    m.ring.opacity = amount
end sub
