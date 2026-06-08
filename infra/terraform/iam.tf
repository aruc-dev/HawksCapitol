resource "aws_iam_role" "paper_node" {
  name               = "${local.name_prefix}-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_role_policy" "paper_secret_read" {
  name   = "${local.name_prefix}-secret-read"
  role   = aws_iam_role.paper_node.id
  policy = data.aws_iam_policy_document.paper_secret_read.json
}

resource "aws_iam_role_policy_attachment" "ssm_managed_instance_core" {
  role       = aws_iam_role.paper_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "paper_node" {
  name = "${local.name_prefix}-instance-profile"
  role = aws_iam_role.paper_node.name
}
