sub Main()
    screen = CreateObject("roSGScreen")
    port = CreateObject("roMessagePort")
    screen.SetMessagePort(port)
    screen.CreateScene("MainScene")
    screen.Show()
    while true
        message = Wait(0, port)
        if Type(message) = "roSGScreenEvent"
            if message.IsScreenClosed() then return
        end if
    end while
end sub
