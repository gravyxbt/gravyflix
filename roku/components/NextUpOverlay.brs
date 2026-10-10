sub init()
    m.top.ObserveField("focusedChild", "onFocus")
    m.okHeld = false
end sub

sub onItem()
    item = m.top.item
    if item = invalid then return
    m.top.FindNode("title").text = AutoplayLabel(item)
    image = "pkg:/images/card-fallback.png"
    if item.landscape_url <> invalid
        if item.landscape_url <> "" then image = item.landscape_url
    else if item.poster_url <> invalid
        if item.poster_url <> "" then image = item.poster_url
    end if
    m.top.FindNode("art").uri = image
    m.okHeld = false
end sub

sub onCountdown()
    m.top.FindNode("countdown").text = "Up next in " + m.top.remaining.ToStr() + " seconds"
end sub

sub onFocus()
    m.top.FindNode("focusBar").visible = m.top.HasFocus()
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if key = "OK"
        if not press
            m.okHeld = false
        else if not m.okHeld
            m.okHeld = true
            m.top.activated++
        end if
        return true
    end if
    if key = "back" and press
        m.top.dismissed++
        return true
    end if
    if press then m.top.releasedFocus++
    ' This node is a child of Video: seeking and transport keys bubble to the existing player.
    return false
end function
