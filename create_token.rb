user = User.find_by(login: "fanglongsheng1106@gmail.com")
perms = Permission.where(active: true).pluck(:name)
puts "Total permissions: #{perms.length}"
token = Token.create!(
  action: "api",
  persistent: true,
  user: user,
  name: "agent-full-access-v2",
  preferences: { permission: perms }
)
puts token.token
