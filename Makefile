.PHONY: plan apply deploy

plan:
	cd terraform && AWS_PROFILE=moon-terraform terraform plan -refresh=false

apply:
	cd terraform && AWS_PROFILE=moon-terraform terraform apply

deploy:
	aws ecs update-service --cluster moon --service moon --force-new-deployment

up:
	aws ecs update-service --cluster moon --service moon --desired-count 1

down:
	aws ecs update-service --cluster moon --service moon --desired-count 0
