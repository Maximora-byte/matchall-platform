package api

// MatchAll integration is deliberately a separate, private-only route set.
// Setting MATCHALL_INTERNAL_KEY disables every public registration/login route.
import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"errors"
	"github.com/gofiber/fiber/v2"
	dbErrors "github.com/ivpn/dns/api/db/errors"
	"github.com/ivpn/dns/api/internal/auth"
	"github.com/ivpn/dns/api/model"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo/options"
	"os"
	"strings"
	"sync"
)

var provisionLock sync.Mutex // This isolated adapter supports exactly one API process.

func (s *APIServer) registerMatchAll() {
	group := s.App.Group("/internal/matchall")
	group.Use(func(c *fiber.Ctx) error {
		want := sha256.Sum256([]byte(os.Getenv("MATCHALL_INTERNAL_KEY")))
		got := sha256.Sum256([]byte(strings.TrimPrefix(c.Get("Authorization"), "Bearer ")))
		if len(os.Getenv("MATCHALL_INTERNAL_KEY")) < 32 || subtle.ConstantTimeCompare(want[:], got[:]) != 1 {
			return c.SendStatus(401)
		}
		subject := c.Get("X-MatchAll-Subject")
		if len(subject) < 1 || len(subject) > 255 {
			return c.SendStatus(400)
		}
		hash := sha256.Sum256([]byte("https://auth.maximoraverse.org/application/o/matchall-dns/\x00" + subject))
		c.Locals("matchall_identity", hex.EncodeToString(hash[:]))
		return c.Next()
	})
	// Host-only disaster recovery. Stop proxies/updater before invoking.
	group.Post("/maintenance/rehydrate", func(c *fiber.Ctx) error {
		if c.Get("X-MatchAll-Subject") != "__maintenance__" {
			return c.SendStatus(403)
		}
		provisionLock.Lock()
		defer provisionLock.Unlock()
		ctx := c.UserContext()
		database := s.Db.GetClient().Database(s.Config.DB.Name)
		cursor, err := database.Collection("blocklists_metadata").Find(ctx, bson.M{})
		if err != nil {
			return c.SendStatus(503)
		}
		var lists []struct {
			ID string `bson:"blocklist_id"`
		}
		if err = cursor.All(ctx, &lists); err != nil {
			return c.SendStatus(503)
		}
		for _, list := range lists {
			if err = s.Cache.Del(ctx, "blocklist:"+list.ID); err != nil {
				return c.SendStatus(503)
			}
			if err = s.Cache.Del(ctx, "blocklist:"+list.ID+":exceptions"); err != nil {
				return c.SendStatus(503)
			}
		}
		cursor, err = database.Collection("blocklists").Find(ctx, bson.M{})
		if err != nil {
			return c.SendStatus(503)
		}
		var parts []struct {
			ID   string `bson:"blocklist_id"`
			Kind string `bson:"kind"`
			Data []byte `bson:"data"`
		}
		if err = cursor.All(ctx, &parts); err != nil {
			return c.SendStatus(503)
		}
		for _, part := range parts {
			id := part.ID
			if part.Kind == "exceptions" {
				id += ":exceptions"
			}
			if len(part.Data) > 0 {
				if err = s.Cache.AddBlocklist(ctx, id, part.Data); err != nil {
					return c.SendStatus(503)
				}
			}
		}
		cursor, err = database.Collection("profiles").Find(ctx, bson.M{})
		if err != nil {
			return c.SendStatus(503)
		}
		var profiles []model.Profile
		if err = cursor.All(ctx, &profiles); err != nil {
			return c.SendStatus(503)
		}
		for _, profile := range profiles {
			if err = s.Cache.DeleteProfileSettings(ctx, profile.ProfileId); err != nil {
				return c.SendStatus(503)
			}
			if err = s.Cache.CreateOrUpdateProfileSettings(ctx, profile.Settings, true); err != nil {
				return c.SendStatus(503)
			}
			if len(profile.Settings.CustomRules) > 0 {
				if err = s.Cache.AddCustomRules(ctx, profile.ProfileId, profile.Settings.CustomRules); err != nil {
					return c.SendStatus(503)
				}
			}
		}
		return c.JSON(fiber.Map{"profiles": len(profiles), "lists": len(lists), "state": "rehydrated"})
	})
	group.Put("/account", func(c *fiber.Ctx) error {
		provisionLock.Lock()
		defer provisionLock.Unlock()
		ctx := c.UserContext()
		key := c.Locals("matchall_identity").(string)
		mappings := s.Db.GetClient().Database(s.Config.DB.Name).Collection("matchall_identities")
		_, err := mappings.UpdateOne(ctx, bson.M{"_id": key}, bson.M{"$setOnInsert": bson.M{"account_id": primitive.NewObjectID().Hex(), "state": "pending"}}, options.Update().SetUpsert(true))
		if err != nil {
			return c.SendStatus(503)
		}
		var mapping struct {
			AccountID string `bson:"account_id"`
			State     string `bson:"state"`
		}
		if err = mappings.FindOne(ctx, bson.M{"_id": key}).Decode(&mapping); err != nil {
			return c.SendStatus(503)
		}
		if mapping.State == "deleted" || mapping.State == "deleting" {
			return c.SendStatus(410)
		}
		// Reconcile on every retry: profiles may have committed before account creation.
		profiles, err := s.Service.GetProfiles(ctx, mapping.AccountID)
		if err != nil {
			return c.SendStatus(503)
		}
		profileID := ""
		if len(profiles) > 0 {
			profileID = profiles[0].ProfileId
		} else {
			profile, err := s.Service.CreateProfile(ctx, "MatchAll default", mapping.AccountID)
			if err != nil {
				return c.SendStatus(503)
			}
			profileID = profile.ProfileId
		}
		_, err = s.Service.GetAccount(ctx, mapping.AccountID)
		if errors.Is(err, dbErrors.ErrAccountNotFound) {
			_, err = s.Db.CreateAccount(ctx, key+"@matchall.invalid", "", mapping.AccountID, profileID)
		}
		if err != nil {
			return c.SendStatus(503)
		}
		_, err = s.Service.UpdateProfile(ctx, mapping.AccountID, profileID, []model.ProfileUpdate{{Operation: "replace", Path: "/settings/statistics/enabled", Value: false}, {Operation: "replace", Path: "/settings/logs/enabled", Value: false}})
		if err != nil {
			return c.SendStatus(503)
		}
		_, err = mappings.UpdateOne(ctx, bson.M{"_id": key}, bson.M{"$set": bson.M{"state": "ready", "profile_id": profileID}})
		if err != nil {
			return c.SendStatus(503)
		}
		return c.JSON(fiber.Map{"account_id": mapping.AccountID, "profile_id": profileID, "state": "ready"})
	})
	group.Delete("/account", func(c *fiber.Ctx) error {
		provisionLock.Lock()
		defer provisionLock.Unlock()
		key := c.Locals("matchall_identity").(string)
		ctx := c.UserContext()
		collection := s.Db.GetClient().Database(s.Config.DB.Name).Collection("matchall_identities")
		var mapping struct {
			AccountID string `bson:"account_id"`
			ProfileID string `bson:"profile_id"`
		}
		if err := collection.FindOne(ctx, bson.M{"_id": key}).Decode(&mapping); err != nil {
			return c.SendStatus(404)
		}
		if _, err := collection.UpdateOne(ctx, bson.M{"_id": key}, bson.M{"$set": bson.M{"state": "deleting"}}); err != nil {
			return c.SendStatus(503)
		}
		// Repeat cache deletion by stored ID to cover an interrupted upstream purge.
		if mapping.ProfileID != "" {
			if err := s.Cache.DeleteProfileSettings(ctx, mapping.ProfileID); err != nil {
				return c.SendStatus(503)
			}
		}
		if err := s.Service.PurgeAccountData(ctx, mapping.AccountID); err != nil {
			return c.SendStatus(503)
		}
		if _, err := collection.UpdateOne(ctx, bson.M{"_id": key}, bson.M{"$set": bson.M{"state": "deleted"}}); err != nil {
			return c.SendStatus(503)
		}
		return c.SendStatus(204)
	})
	group.Use(func(c *fiber.Ctx) error {
		var mapping struct {
			AccountID string `bson:"account_id"`
			State     string `bson:"state"`
		}
		err := s.Db.GetClient().Database(s.Config.DB.Name).Collection("matchall_identities").FindOne(c.UserContext(), bson.M{"_id": c.Locals("matchall_identity")}).Decode(&mapping)
		if err != nil || mapping.State != "ready" {
			return c.SendStatus(409)
		}
		c.Locals(auth.ACCOUNT_ID, mapping.AccountID)
		return c.Next()
	})
	group.Get("/profiles", s.getProfiles())
	group.Get("/profiles/:id", s.getProfile())
	// Only the required profile operations are exposed; no passwords, sessions, recovery or logs.
	group.Get("/blocklists", s.getBlocklists())
	group.Post("/profiles/:id/blocklists", s.enableBlocklists())
	group.Delete("/profiles/:id/blocklists", s.disableBlocklists())
	group.Post("/profiles/:id/custom_rules", s.createProfileCustomRule())
	group.Delete("/profiles/:profile_id/custom_rules/:custom_rule_id", s.deleteProfileCustomRule())
	group.Get("/services", s.getServicesCatalog())
	group.Post("/profiles/:id/services", s.enableServices())
	group.Delete("/profiles/:id/services", s.disableServices())
	group.Post("/profiles/:id/custom_rules/batch", s.createProfileCustomRulesBatch())
	group.Patch("/profiles/:profile_id/custom_rules/:custom_rule_id", s.updateProfileCustomRule())
	group.Patch("/profiles/:id/custom_rule_groups", s.updateProfileCustomRuleGroups())
	// Narrow patch surface: no log, recursor, or arbitrary profile switches.
	group.Patch("/profiles/:id/rebinding", func(c *fiber.Ctx) error {
		var body struct {
			Enabled *bool `json:"enabled"`
		}
		if err := c.BodyParser(&body); err != nil || body.Enabled == nil {
			return c.SendStatus(400)
		}
		profile, err := s.Service.UpdateProfile(c.UserContext(), auth.GetAccountID(c), c.Params("id"), []model.ProfileUpdate{{Operation: "replace", Path: "/settings/security/rebinding_protection/enabled", Value: *body.Enabled}})
		if err != nil {
			return HandleError(c, err, "Failed to update rebinding protection")
		}
		return c.JSON(profile)
	})
	group.Get("/profiles/:id/statistics", s.getStatistics())
}
